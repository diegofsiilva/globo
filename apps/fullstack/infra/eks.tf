# Cluster Kubernetes que orquestra o caminho SINCRONO do Argus.
#
# O que ele substitui: ate a Sprint 3 a API de leitura rodava em instancias de
# um ASG (asg.tf, removido na Sprint 4) que subiam o container a mao, pelo user_data
# (`dnf install docker && docker pull && docker run`). Aquilo e orquestracao de
# container feita numa VM: sem rolling deploy, sem reposicao do container por
# health -- so o target group derrubando a instancia inteira -- e com
# `health_check_grace_period = 300s` apenas para cobrir boot, instalacao e pull.
#
# O que ele NAO substitui: o caminho assincrono (workers de SQS, processing,
# simulator, loader) continua no ECS Fargate, intocado. La o Fargate ja entrega
# estado desejado, rolling deploy e health check, e o IAM por task e melhor do
# que este cluster consegue oferecer -- ver a nota sobre IRSA abaixo.
#
# Modo Auto: sem node group, sem Karpenter instalado a mao, sem AWS Load
# Balancer Controller por Helm. Essa ultima parte e o que torna o Auto Mode a
# unica opcao viavel neste ambiente: o controlador instalado por Helm precisaria
# de IRSA, e o Learner Lab nega iam:CreateRole e iam:CreateOpenIDConnectProvider.
# No Auto Mode quem provisiona o ALB e a propria AWS, usando a role do CLUSTER.

locals {
  # O cluster so existe quando a rede dedicada existe. O Auto Mode precisa de
  # sub-redes privadas com saida por NAT, que e exatamente o que create_network
  # entrega; sem ela o stack cai na VPC default, onde nao ha rota privada ate o
  # RDS -- e um cluster ali seria um cluster que nao alcanca o banco.
  criar_eks = var.create_eks && var.create_network

  eks_name = "${local.name}-eks"

  # Os papeis do EKS ja existem na conta do Learner Lab e NAO podem ser criados:
  # iam:CreateRole e negado. O nome carrega um prefixo de sessao que muda a cada
  # lab novo, entao ele e DESCOBERTO por regex e nunca escrito. As variaveis
  # eks_*_role_arn existem como escape, caso iam:ListRoles tambem seja negado
  # numa turma futura -- nesta conta ele e permitido (verificado).
  eks_cluster_role_arn = (
    var.eks_cluster_role_arn != ""
    ? var.eks_cluster_role_arn
    : try(tolist(data.aws_iam_roles.eks_cluster[0].arns)[0], "")
  )

  eks_node_role_arn = (
    var.eks_node_role_arn != ""
    ? var.eks_node_role_arn
    : try(tolist(data.aws_iam_roles.eks_node[0].arns)[0], "")
  )
}

data "aws_iam_roles" "eks_cluster" {
  count = local.criar_eks && var.eks_cluster_role_arn == "" ? 1 : 0

  name_regex = var.eks_cluster_role_name_regex
}

data "aws_iam_roles" "eks_node" {
  count = local.criar_eks && var.eks_node_role_arn == "" ? 1 : 0

  name_regex = var.eks_node_role_name_regex
}

resource "aws_eks_cluster" "main" {
  count = local.criar_eks ? 1 : 0

  name     = local.eks_name
  role_arn = local.eks_cluster_role_arn
  version  = var.eks_version

  # Auto Mode EXIGE false. Os add-ons de rede e de armazenamento passam a ser
  # gerenciados pela AWS, e deixar os self-managed ligados faz o CreateCluster
  # falhar com InvalidParameterException -- uma falha que aparece 10 minutos
  # depois do apply comecar.
  bootstrap_self_managed_addons = false

  access_config {
    # API e nao CONFIG_MAP: o modo antigo exigiria editar o ConfigMap aws-auth
    # dentro do cluster, o que o Terraform nao alcanca sem o provider
    # kubernetes. Com API, quem da acesso e aws_eks_access_entry, abaixo.
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  compute_config {
    enabled    = true
    node_pools = var.eks_node_pools

    # iam:PassRole sobre este papel e permitido no lab (verificado). O papel traz
    # AmazonEKSWorkerNodePolicy, AmazonEKS_CNI_Policy e
    # AmazonEC2ContainerRegistryReadOnly -- o minimo, e nada de SQS ou S3.
    #
    # E o suficiente porque NENHUM pod deste cluster fala com a AWS: o backend
    # nao tem boto3 (ver backend/pyproject.toml, que registra a remocao) e o
    # frontend e nginx servindo arquivo estatico. Quem precisa de SQS e S3 e o
    # caminho assincrono, que continua no Fargate com role por task.
    node_role_arn = local.eks_node_role_arn
  }

  kubernetes_network_config {
    # Liga o controlador de ALB embutido. E ele que le os objetos Ingress e cria
    # o balanceador, sem IRSA e sem Helm.
    elastic_load_balancing {
      enabled = true
    }
  }

  storage_config {
    block_storage {
      enabled = true
    }
  }

  vpc_config {
    # Os node pools padrao do Auto Mode escolhem entre as sub-redes do cluster.
    # Oferecer tambem as publicas lhes deu IP publico no ensaio de 24/09. O ALB
    # descobre as sub-redes publicas pela tag kubernetes.io/role/elb em vpc.tf;
    # elas nao precisam integrar a lista de sub-redes dos nos.
    subnet_ids = local.private_subnet_ids

    endpoint_private_access = true

    # Publico: sem isso, todo kubectl teria de passar pelo bastion. Numa conta
    # de producao o certo seria false com acesso por VPN; aqui a sessao do lab
    # dura horas e o bastion so existe quando var.create_bastion esta ligado.
    endpoint_public_access = true
    public_access_cidrs    = var.eks_public_access_cidrs
  }

  tags = {
    Name      = local.eks_name
    Component = "kubernetes"
  }

  lifecycle {
    precondition {
      condition     = local.eks_cluster_role_arn != "" && local.eks_node_role_arn != ""
      error_message = "Papeis LabEks* nao encontrados nesta conta. Rode 'make -C .. eks-roles' e cole os ARNs em eks_cluster_role_arn / eks_node_role_arn no terraform.tfvars."
    }
  }
}

# metrics-server: o HPA depende dele e o Auto Mode NAO o instala.
#
# Um cluster recem-criado nasce com kube-system vazio e sem o APIService
# v1beta1.metrics.k8s.io. Sem ele o HPA de k8s/base/backend-hpa.yaml fica em
# `<unknown>/60%` com ScalingActive=False e nunca escala -- foi assim no lab
# limpo de 18/09/2026 (artefatos/evidencias/carga-kubernetes.txt). O contorno
# manual foi `aws eks create-addon --addon-name metrics-server`; aqui ele vira
# parte do stack, e `cpu: 0%/60%` aparece uns dois minutos depois do apply.
#
# `bootstrap_self_managed_addons = false` no cluster nao conflita: aquele flag
# so desliga os add-ons self-managed de rede (vpc-cni, kube-proxy, coredns),
# que o Auto Mode substitui. Add-on gerenciado declarado por aws_eks_addon
# continua permitido -- e e o unico jeito de instala-lo sem Helm nem IRSA.
#
# Sem `addon_version` de proposito: o provider escolhe a versao padrao
# compativel com var.eks_version, e fixar uma aqui seria mais um numero a
# atualizar a cada upgrade do cluster.
#
# Efeito colateral em `make k8s-scale-zero`: os pods do metrics-server ficam em
# kube-system, entao o Karpenter mantem ao menos um no pequeno de pe mesmo com
# a aplicacao zerada. Para chegar a zero nos e preciso destruir o cluster.
resource "aws_eks_addon" "metrics_server" {
  count = local.criar_eks ? 1 : 0

  cluster_name = aws_eks_cluster.main[0].name
  addon_name   = "metrics-server"

  # OVERWRITE: se ja houver um metrics-server instalado a mao no cluster (um
  # `kubectl apply` do components.yaml, como faz o `kind-up`), o add-on assume
  # os objetos em vez de falhar em conflito de campo. Nao cobre add-on criado
  # por `aws eks create-addon` -- esse precisa de `terraform import
  # 'aws_eks_addon.metrics_server[0]' <cluster>:metrics-server`.
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  tags = {
    Name      = "${local.eks_name}-metrics-server"
    Component = "kubernetes"
  }

  depends_on = [aws_eks_cluster.main]
}

# Acesso ao cluster para quem NAO aplicou o Terraform.
#
# `bootstrap_cluster_creator_admin_permissions` cobre apenas o principal que
# rodou o apply. Sem estas entradas, o colega que rodar `aws eks
# update-kubeconfig` recebe "You must be logged in to the server (Unauthorized)"
# -- um erro que parece de credencial da AWS, mas e de autorizacao do cluster.
resource "aws_eks_access_entry" "admins" {
  for_each = local.criar_eks ? toset(var.eks_extra_admin_role_arns) : toset([])

  cluster_name  = aws_eks_cluster.main[0].name
  principal_arn = each.value
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "admins" {
  for_each = aws_eks_access_entry.admins

  cluster_name  = aws_eks_cluster.main[0].name
  principal_arn = each.value.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }
}
