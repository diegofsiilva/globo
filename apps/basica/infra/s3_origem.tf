# Bucket de origem: o dump imutavel e o Parquet derivado dele.
#
# O `.sql` continua sendo a fonte de verdade; o Parquet e formato de transporte.
# Os dois sobem aqui para que a proveniencia feche por completo -- daqui a seis
# meses, "de onde veio esta linha da bronze" tem que ter resposta sem depender
# do que sobrou no Downloads de quem rodou o ETL.
#
# Versionamento ligado porque este bucket guarda a UNICA copia do dado cedido
# pelo parceiro que nao esta num laptop. Um `aws s3 sync --delete` distraido em
# bucket sem versao apaga 4 GB que a Globo nao vai ceder de novo.
#
# O bucket em si nasce FORA do Terraform (aws s3api create-bucket), pelo
# mesmo motivo de flow_logs/alb_logs (ver locals.tf): a SCP do Academy nega a
# releitura que o recurso `aws_s3_bucket` faz logo depois de criar ou
# importar, e nesta versao do provider isso derruba o Terraform com panic em
# vez de so falhar. `local.origem_bucket_name` mantem o nome deterministico.

resource "aws_s3_bucket_versioning" "origem" {
  bucket = local.origem_bucket_name

  versioning_configuration {
    status = "Enabled"
  }
}

# Ao contrario do bucket do dashboard, este e privado de verdade: e dado do
# parceiro, nao HTML publico.
resource "aws_s3_bucket_public_access_block" "origem" {
  bucket = local.origem_bucket_name

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "origem" {
  bucket = local.origem_bucket_name

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versao antiga do dump ocupa 4 GB cada. Sem expiracao, tres re-uploads viram
# 12 GB de storage que ninguem vai consultar.
resource "aws_s3_bucket_lifecycle_configuration" "origem" {
  bucket = local.origem_bucket_name

  rule {
    id     = "expira-versao-antiga"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  depends_on = [aws_s3_bucket_versioning.origem]
}
