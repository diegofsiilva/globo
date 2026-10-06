"""Cria uma EC2 temporária, mede Python/Golang e recolhe evidências sem segredos."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from benchmarks.medicao.executar import BENCHMARKS, PROCESSING, REPO, STAGES, resumo


def sanitizar(text: str) -> str:
    """Remove identificadores de conta, ARNs e URLs das mensagens externas."""
    text = re.sub(r"\b\d{12}\b", "[conta]", text)
    text = re.sub(r"arn:[^\s\"']+", "[ARN]", text)
    return re.sub(r"(?:https?://|s3://)[^\s\"']+", "[endereço]", text)


class AwsCli:
    """Executa somente chamadas no perfil e região escolhidos para a rodada."""

    def __init__(self, region: str):
        """Fixa g4 e evita pager ou encaminhamento implícito para outra conta."""
        self.region = region

    def call(self, *arguments: str, missing_ok: bool = False):
        """Captura respostas sem imprimir valores privados; propaga erros sanitizados."""
        result = subprocess.run(
            [
                "aws",
                *arguments,
                "--profile",
                "g4",
                "--region",
                self.region,
                "--output",
                "json",
                "--cli-connect-timeout",
                "10",
                "--cli-read-timeout",
                "30",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "AWS_PAGER": ""},
            timeout=90,
        )
        if result.returncode:
            if missing_ok and any(
                value in result.stderr
                for value in ("NoSuchKey", "Not Found", "404", "NoSuchBucket")
            ):
                return None
            raise RuntimeError(sanitizar(result.stderr))
        content = result.stdout.strip()
        return json.loads(content) if content else None


def pacote(path: Path) -> tuple[str, dict]:
    """Empacota apenas código, testes e dados sintéticos; normaliza textos para LF."""
    paths = [REPO / "apps/fullstack/Makefile"]
    for project in (PROCESSING, PROCESSING.parent / "common"):
        paths += [project / "pyproject.toml"]
        if (project / "uv.lock").exists():
            paths.append(project / "uv.lock")
        paths += list((project / "src").rglob("*.py"))
        paths += list((project / "src").rglob("*.json"))
    paths += list((PROCESSING / "tests").glob("*.py"))
    paths += list(BENCHMARKS.rglob("*.py"))
    paths += list(BENCHMARKS.rglob("*.go"))
    paths += list((BENCHMARKS / "fixtures").glob("*.json"))
    paths += [BENCHMARKS / "golang/go.mod", BENCHMARKS / "medicao/bootstrap_aws.sh"]
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    source_hashes = {}
    with tarfile.open(path, "w:gz") as archive:
        for source in sorted(set(paths)):
            relative = source.relative_to(REPO).as_posix()
            data = source.read_text(encoding="utf-8").encode("utf-8")
            source_hashes[relative] = hashlib.sha256(data).hexdigest()
            info = tarfile.TarInfo(relative)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
        snapshot = {"original_revision": revision, "source_files_sha256": source_hashes}
        data = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode()
        info = tarfile.TarInfo("source_snapshot.json")
        info.size, info.mode, info.mtime = len(data), 0o644, 0
        archive.addfile(info, io.BytesIO(data))
    return hashlib.sha256(path.read_bytes()).hexdigest(), snapshot


def runtimes(go_version: str, uv_version: str) -> dict:
    """Consulta checksums oficiais antes de enviar instaladores para a instância."""
    with urllib.request.urlopen(
        "https://go.dev/dl/?mode=json&include=all", timeout=30
    ) as response:
        releases = json.load(response)
    release = next(r for r in releases if r["version"] == f"go{go_version}")
    go = next(
        f
        for f in release["files"]
        if f["os"] == "linux" and f["arch"] == "arm64" and f["kind"] == "archive"
    )
    uv_url = (
        f"https://github.com/astral-sh/uv/releases/download/{uv_version}/"
        "uv-aarch64-unknown-linux-gnu.tar.gz"
    )
    with urllib.request.urlopen(uv_url + ".sha256", timeout=30) as response:
        uv_sha = response.read().decode().split()[0]
    if not re.fullmatch(r"[a-f0-9]{64}", uv_sha):
        raise ValueError("Checksum oficial do uv inválido")
    return {
        "go_url": f"https://go.dev/dl/{go['filename']}",
        "go_sha": go["sha256"],
        "uv_url": uv_url,
        "uv_sha": uv_sha,
    }


def bootstrap(parameters: dict) -> str:
    """Preenche o template com argumentos escapados, sem credenciais no user data."""
    content = (BENCHMARKS / "medicao/bootstrap_aws.sh").read_text(encoding="utf-8")
    for key, value in parameters.items():
        content = content.replace(f"@@{key}@@", shlex.quote(str(value)))
    if "@@" in content or len(content.encode()) > 16 * 1024:
        raise ValueError("User data incompleto ou maior que 16 KiB")
    return content


def salvar_estado(path: Path, state: dict) -> None:
    """Mantém identificadores de recuperação em arquivo privado fora do repositório."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def limpar(cli: AwsCli, state: dict) -> dict:
    """Encerra exclusivamente recursos criados pela execução e registra falhas."""
    result = {
        "instance_terminated": False,
        "security_group_deleted": False,
        "bucket_deleted": False,
        "errors": [],
    }
    if state.get("instance"):
        try:
            cli.call("ec2", "terminate-instances", "--instance-ids", state["instance"])
            cli.call(
                "ec2", "wait", "instance-terminated", "--instance-ids", state["instance"]
            )
            result["instance_terminated"] = True
        except Exception as error:
            result["errors"].append(sanitizar(str(error)))
    if state.get("security_group"):
        try:
            cli.call(
                "ec2", "delete-security-group", "--group-id", state["security_group"]
            )
            result["security_group_deleted"] = True
        except Exception as error:
            result["errors"].append(sanitizar(str(error)))
    if state.get("bucket"):
        try:
            objects = cli.call("s3api", "list-objects-v2", "--bucket", state["bucket"])
            for obj in objects.get("Contents", []):
                cli.call(
                    "s3api",
                    "delete-object",
                    "--bucket",
                    state["bucket"],
                    "--key",
                    obj["Key"],
                )
            cli.call("s3api", "delete-bucket", "--bucket", state["bucket"])
            result["bucket_deleted"] = True
        except Exception as error:
            result["errors"].append(sanitizar(str(error)))
    return result


def executar(args) -> None:
    """Provisiona, observa a rodada e baixa resultados antes de remover a estrutura."""
    if args.output_dir.exists():
        raise ValueError("Pasta de evidências já existe; escolha outra para preservá-la")
    cli = AwsCli(args.region)
    account = cli.call("sts", "get-caller-identity")["Account"]
    cli.call(
        "iam", "get-instance-profile", "--instance-profile-name", "LabInstanceProfile"
    )
    vpcs = cli.call("ec2", "describe-vpcs", "--filters", "Name=is-default,Values=true")[
        "Vpcs"
    ]
    if len(vpcs) != 1:
        raise ValueError("É necessária uma VPC padrão para este ambiente isolado")
    subnets = cli.call(
        "ec2",
        "describe-subnets",
        "--filters",
        f"Name=vpc-id,Values={vpcs[0]['VpcId']}",
        "Name=default-for-az,Values=true",
    )["Subnets"]
    subnet = sorted(subnets, key=lambda s: s["AvailabilityZone"])[0]
    ami = cli.call(
        "ssm",
        "get-parameter",
        "--name",
        "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64",
    )["Parameter"]["Value"]
    instance_type = cli.call(
        "ec2", "describe-instance-types", "--instance-types", args.instance_type
    )["InstanceTypes"][0]
    if "arm64" not in instance_type["ProcessorInfo"]["SupportedArchitectures"]:
        raise ValueError("O executor remoto desta rodada requer instância ARM64")
    versions = runtimes(args.go_version, args.uv_version)
    run_id = uuid.uuid4().hex[:16]
    name = f"argus-benchmark-{run_id}"
    state = {"region": args.region, "run_id": run_id}
    state_file = Path(tempfile.gettempdir()) / f"{name}.json"
    args.output_dir.mkdir(parents=True)
    cleanup = None
    try:
        with tempfile.TemporaryDirectory(prefix="argus-aws-payload-") as temporary:
            directory = Path(temporary)
            archive = directory / "source.tar.gz"
            source_sha, snapshot = pacote(archive)
            bucket = f"{name}-{account}"
            create_args = ["s3api", "create-bucket", "--bucket", bucket]
            if args.region != "us-east-1":
                create_args += [
                    "--create-bucket-configuration",
                    f"LocationConstraint={args.region}",
                ]
            cli.call(*create_args)
            state["bucket"] = bucket
            salvar_estado(state_file, state)
            cli.call(
                "s3api",
                "put-public-access-block",
                "--bucket",
                bucket,
                "--public-access-block-configuration",
                json.dumps(
                    {
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True,
                    }
                ),
            )
            cli.call(
                "s3api",
                "put-bucket-encryption",
                "--bucket",
                bucket,
                "--server-side-encryption-configuration",
                json.dumps(
                    {
                        "Rules": [
                            {
                                "ApplyServerSideEncryptionByDefault": {
                                    "SSEAlgorithm": "AES256"
                                }
                            }
                        ]
                    }
                ),
            )
            cli.call(
                "s3api",
                "put-object",
                "--bucket",
                bucket,
                "--key",
                "source.tar.gz",
                "--body",
                str(archive),
            )
            sg = cli.call(
                "ec2",
                "create-security-group",
                "--group-name",
                name,
                "--description",
                "Execucao temporaria do benchmark Argus",
                "--vpc-id",
                vpcs[0]["VpcId"],
            )["GroupId"]
            state["security_group"] = sg
            salvar_estado(state_file, state)
            parameters = {
                "REGION": args.region,
                "SOURCE_URI": f"s3://{bucket}/source.tar.gz",
                "STATUS_URI": f"s3://{bucket}/status.json",
                "OUTPUT_URI": f"s3://{bucket}/output/",
                "LOG_URI": f"s3://{bucket}/run.log",
                "GO_URL": versions["go_url"],
                "GO_SHA256": versions["go_sha"],
                "UV_URL": versions["uv_url"],
                "UV_SHA256": versions["uv_sha"],
                "SOURCE_SHA256": source_sha,
                "PYTHON_VERSION": args.python_version,
                "ROUNDS": args.rounds,
                "LABEL": args.label,
                "WARMUPS": args.warmups,
                "REPETITIONS": args.repetitions,
            }
            script = directory / "userdata.sh"
            script.write_text(bootstrap(parameters), encoding="utf-8", newline="\n")
            request = {
                "ImageId": ami,
                "InstanceType": args.instance_type,
                "MinCount": 1,
                "MaxCount": 1,
                "IamInstanceProfile": {"Name": "LabInstanceProfile"},
                "NetworkInterfaces": [
                    {
                        "DeviceIndex": 0,
                        "SubnetId": subnet["SubnetId"],
                        "Groups": [sg],
                        "AssociatePublicIpAddress": True,
                    }
                ],
                "InstanceInitiatedShutdownBehavior": "terminate",
                "MetadataOptions": {"HttpTokens": "required", "HttpEndpoint": "enabled"},
                "BlockDeviceMappings": [
                    {
                        "DeviceName": "/dev/xvda",
                        "Ebs": {
                            "VolumeSize": 12,
                            "VolumeType": "gp3",
                            "Encrypted": True,
                            "DeleteOnTermination": True,
                        },
                    }
                ],
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": name},
                            {"Key": "Project", "Value": "argus"},
                            {"Key": "Purpose", "Value": "benchmark"},
                            {"Key": "RunId", "Value": run_id},
                        ],
                    }
                ],
            }
            request_file = directory / "request.json"
            request_file.write_text(json.dumps(request), encoding="utf-8")
            launched = cli.call(
                "ec2",
                "run-instances",
                "--cli-input-json",
                f"file://{request_file}",
                "--user-data",
                f"file://{script}",
            )
            state["instance"] = launched["Instances"][0]["InstanceId"]
            salvar_estado(state_file, state)
            print(
                f"EC2 temporária criada: {args.instance_type}; {args.rounds} rodadas.",
                flush=True,
            )
            deadline, previous_phase = time.monotonic() + args.timeout, None
            while time.monotonic() < deadline:
                status_file = directory / "status.json"
                status = cli.call(
                    "s3api",
                    "get-object",
                    "--bucket",
                    bucket,
                    "--key",
                    "status.json",
                    str(status_file),
                    missing_ok=True,
                )
                if status is not None:
                    progress = json.loads(status_file.read_text(encoding="utf-8"))
                    phase = progress["phase"]
                    if phase != previous_phase:
                        print(f"AWS: {phase}", flush=True)
                        previous_phase = phase
                    if phase == "completed":
                        break
                    if phase == "failed":
                        raise RuntimeError(
                            f"Execução remota falhou: código {progress['exit_code']}"
                        )
                time.sleep(15)
            else:
                raise TimeoutError("A execução remota não terminou dentro do prazo")
            for number in range(1, args.rounds + 1):
                relative = f"rodada-{number:02d}/resultados.json"
                destination = args.output_dir / relative
                destination.parent.mkdir()
                cli.call(
                    "s3api",
                    "get-object",
                    "--bucket",
                    bucket,
                    "--key",
                    f"output/{relative}",
                    str(destination),
                )
                result = json.loads(destination.read_text(encoding="utf-8"))
                if result["protocol"]["parity_cases"] != 54:
                    raise ValueError("Paridade remota incompleta")
                for workload in result["workloads"]:
                    for language in ("python", "go"):
                        runtime = workload[language]
                        for stage in STAGES:
                            samples = runtime["samples_ns"][stage]
                            if len(samples) != args.repetitions:
                                raise ValueError(
                                    "Quantidade incorreta de amostras remotas"
                                )
                            if resumo(samples) != runtime["summary"][stage]:
                                raise ValueError("Estatísticas remotas divergentes")
                for path, digest in result["source_files_sha256"].items():
                    if snapshot["source_files_sha256"].get(path) != digest:
                        raise ValueError(f"Fonte remota diverge do pacote: {path}")
            metadata = {
                "schema_version": 1,
                "label": args.label,
                "region": args.region,
                "instance_type": args.instance_type,
                "architecture": "arm64",
                "vcpus": instance_type["VCpuInfo"]["DefaultVCpus"],
                "memory_mib": instance_type["MemoryInfo"]["SizeInMiB"],
                "processor": instance_type["ProcessorInfo"],
                "rounds": args.rounds,
                "original_source_revision": snapshot["original_revision"],
                "source_archive_sha256": source_sha,
                "source_files_sha256": snapshot["source_files_sha256"],
                "scope": "calculo_sem_banco",
                "runtime_checksums": versions,
            }
            (args.output_dir / "ambiente.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                "Amostras, paridade, estatísticas e hashes remotos conferidos.",
                flush=True,
            )
    except Exception:
        if state.get("bucket"):
            with tempfile.TemporaryDirectory(prefix="argus-aws-log-") as log_dir:
                log_file = Path(log_dir) / "run.log"
                try:
                    cli.call(
                        "s3api",
                        "get-object",
                        "--bucket",
                        state["bucket"],
                        "--key",
                        "run.log",
                        str(log_file),
                        missing_ok=True,
                    )
                    if log_file.exists():
                        print(
                            sanitizar("\n".join(log_file.read_text().splitlines()[-35:]))
                        )
                except Exception:
                    pass
        raise
    finally:
        cleanup = limpar(cli, state)
        (args.output_dir / "limpeza.json").write_text(
            json.dumps(cleanup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        state["cleanup"] = cleanup
        salvar_estado(state_file, state)
        print(
            "Limpeza concluída."
            if not cleanup["errors"]
            else "Limpeza pendente; consultar limpeza.json.",
            flush=True,
        )
    if cleanup["errors"]:
        raise RuntimeError("Existem recursos temporários que precisam de limpeza")


def main() -> None:
    """Recebe os parâmetros da rodada pelo alvo benchmark-aws do Makefile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--instance-type", default="c6g.medium")
    parser.add_argument("--python-version", default="3.14.4")
    parser.add_argument("--go-version", default="1.27.1")
    parser.add_argument("--uv-version", default="0.12.5")
    parser.add_argument("--label", default="rodada-aws")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--output-dir", type=Path, default=REPO / "artefatos/benchmark/resultados-aws"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", args.label):
        parser.error("Label deve conter apenas letras, números, hífen ou sublinhado")
    if args.rounds < 1 or args.warmups < 3 or args.repetitions < 20:
        parser.error("Usar pelo menos uma rodada, três aquecimentos e vinte amostras")
    executar(args)


if __name__ == "__main__":
    main()
