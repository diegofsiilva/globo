# Rede dedicada do Argus: VPC, sub-redes publicas e privadas, IGW e NAT.
#
# Ate a v3 tudo rodava na VPC default da conta, com `assign_public_ip = true`
# nas tasks. Isso funcionava, mas dava a cada carga um endereco roteavel da
# internet -- a task nao aceitava conexao de fora (o security group nao tem
# regra de entrada), porem a superficie existia e nao havia como reduzi-la sem
# uma rede propria.
#
# Aqui a saida passa a ser assimetrica: o NAT Gateway deixa a carga privada
# ALCANCAR a internet (atualizar pacote, puxar imagem do ECR, falar com a API do
# Secrets Manager) sem que a internet consiga iniciar conexao de volta. E isso,
# e nao o nome da sub-rede, que a torna privada.
#
# Duas zonas de disponibilidade porque o Application Load Balancer EXIGE no
# minimo duas sub-redes em AZs distintas. Nao e preferencia de projeto: sem a
# segunda AZ o recurso `aws_lb` nem chega a ser criado.

# As AZs saem da conta, e nao de literais "us-east-1a".
#
# O Learner Lab distribui as zonas por conta: o "us-east-1a" de uma conta pode
# ser o hardware que a outra enxerga como "us-east-1c", e nem toda conta recebe
# a mesma lista. Fixar o nome faz o apply falhar numa conta e passar noutra, com
# a causa aparecendo como "subnet invalida" muito depois do erro real.
data "aws_availability_zones" "available" {
  count = var.create_network ? 1 : 0
  state = "available"
}

locals {
  azs = var.create_network ? (
    length(var.azs) > 0
    ? var.azs
    : slice(data.aws_availability_zones.available[0].names, 0, 2)
  ) : []

  # As faixas saem de `vpc_cidr`, e nao de literais.
  #
  # Com listas fixas, trocar `vpc_cidr` para 10.42.0.0/16 e esquecer as sub-redes
  # deixa 10.0.0.0/24 pendurado fora da VPC: o apply quebra com
  # "InvalidSubnet.Range", num erro que aponta para a sub-rede e nao para a
  # variavel que a causou. Derivando, a segunda faixa acompanha a primeira.
  #
  # O salto de 10 no indice das privadas e legibilidade: olhando um IP num flow
  # log, o terceiro octeto ja diz de que lado da rede ele veio.
  public_cidrs = var.create_network ? (
    length(var.public_subnet_cidrs) > 0
    ? var.public_subnet_cidrs
    : [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i)]
  ) : []

  private_cidrs = var.create_network ? (
    length(var.private_subnet_cidrs) > 0
    ? var.private_subnet_cidrs
    : [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 10)]
  ) : []
}

resource "aws_vpc" "main" {
  count = var.create_network ? 1 : 0

  cidr_block = var.vpc_cidr

  # Os dois sao obrigatorios para o RDS. Sem `enable_dns_hostnames` a instancia
  # nao recebe o nome DNS publico do endpoint, e a DATABASE_URL montada em
  # locals.tf aponta para um host que nao resolve de dentro da propria VPC.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.name}-vpc"
  }
}

# --------------------------------------------------------------------------- #
# Sub-redes
# --------------------------------------------------------------------------- #

# Publicas: ALB, NAT Gateway e bastion. Sao os tres unicos recursos que tem
# motivo para receber conexao vinda de fora ou para ter endereco roteavel.
resource "aws_subnet" "public" {
  count = var.create_network ? length(local.azs) : 0

  vpc_id            = aws_vpc.main[0].id
  cidr_block        = local.public_cidrs[count.index]
  availability_zone = local.azs[count.index]

  # O bastion e o NAT precisam de IP publico. Ligar aqui evita repetir
  # `associate_public_ip_address` em cada recurso da sub-rede.
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name}-public-${count.index}"
    Tier = "public"

    # Descoberta de sub-rede pelo controlador de load balancer do EKS: e por
    # esta tag que ele sabe onde criar o ALB do Ingress. Sem ela o Ingress fica
    # para sempre sem endereco, e a mensagem do controlador fala em "unable to
    # discover subnets" -- longe daqui.
    #
    # Estatica, e nao condicionada a var.create_eks por `aws_ec2_tag`: o
    # aws_subnet calcula o diff de tags contra ESTE bloco e remove o que nao
    # estiver nele, entao um aws_ec2_tag no mesmo recurso produziria um apply
    # que adiciona e o seguinte que remove, para sempre. A tag e inerte quando
    # nao ha cluster.
    "kubernetes.io/role/elb" = "1"
  }
}

# Privadas: instancias do Auto Scaling Group, tasks Fargate e o subnet group do
# RDS. Nada aqui tem endereco publico.
resource "aws_subnet" "private" {
  count = var.create_network ? length(local.azs) : 0

  vpc_id            = aws_vpc.main[0].id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = local.azs[count.index]

  tags = {
    Name = "${local.name}-private-${count.index}"
    Tier = "private"

    # Par da tag das publicas: marca onde um balanceador INTERNO nasceria. Os
    # nos do Auto Mode tambem vivem aqui. Ver a nota em aws_subnet.public sobre
    # por que ela e estatica.
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# --------------------------------------------------------------------------- #
# Saida para a internet
# --------------------------------------------------------------------------- #

resource "aws_internet_gateway" "main" {
  count = var.create_network ? 1 : 0

  vpc_id = aws_vpc.main[0].id

  tags = {
    Name = "${local.name}-igw"
  }
}

resource "aws_eip" "nat" {
  count = var.create_network ? 1 : 0

  domain = "vpc"

  # O EIP so consegue ser associado depois que a VPC tem gateway. Sem isto o
  # apply falha de forma intermitente, dependendo da ordem que o Terraform
  # escolher para o grafo.
  depends_on = [aws_internet_gateway.main]

  tags = {
    Name = "${local.name}-nat-eip"
  }
}

# UM NAT Gateway, e nao um por zona de disponibilidade.
#
# A recomendacao da AWS para producao e um por AZ, justamente para que a queda
# de uma zona nao leve junto a saida da outra. Aqui e um so, por custo: cada NAT
# custa ~US$ 32/mes de hora parada mais o trafego, e o orcamento do Learner Lab
# nao comporta dois.
#
# A consequencia esta assumida e documentada (infraestrutura-integracao.md,
# secao 5.1): se a AZ do NAT cair, as instancias da OUTRA zona continuam
# servindo trafego pelo ALB -- o caminho de leitura nao passa pelo NAT -- mas
# perdem a saida para a internet, entao nao conseguem puxar imagem nova nem
# renovar credencial. O ASG nao consegue subir instancia nova ali ate a zona
# voltar.
resource "aws_nat_gateway" "main" {
  count = var.create_network ? 1 : 0

  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id

  depends_on = [aws_internet_gateway.main]

  tags = {
    Name = "${local.name}-nat"
  }
}

# --------------------------------------------------------------------------- #
# Tabelas de rota
# --------------------------------------------------------------------------- #

# Publica: rota padrao para o Internet Gateway, que e simetrico -- deixa sair e
# deixa entrar.
resource "aws_route_table" "public" {
  count = var.create_network ? 1 : 0

  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }

  tags = {
    Name = "${local.name}-rt-public"
  }
}

# Privada: rota padrao para o NAT, que e assimetrico -- deixa sair e NAO deixa
# entrar. A ausencia de qualquer rota para o IGW nesta tabela e o que impede
# uma conexao iniciada de fora de chegar aqui, mesmo que um security group
# fosse aberto por engano.
resource "aws_route_table" "private" {
  count = var.create_network ? 1 : 0

  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }

  tags = {
    Name = "${local.name}-rt-private"
  }
}

resource "aws_route_table_association" "public" {
  count = var.create_network ? length(aws_subnet.public) : 0

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

# As duas sub-redes privadas compartilham a mesma tabela porque compartilham o
# mesmo NAT. Com um NAT por AZ seriam duas tabelas, uma por zona.
resource "aws_route_table_association" "private" {
  count = var.create_network ? length(aws_subnet.private) : 0

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

# --------------------------------------------------------------------------- #
# Gateway endpoint de S3
# --------------------------------------------------------------------------- #

# Gateway endpoint e GRATIS -- diferente do endpoint de interface, que custa
# ~US$ 7/mes por AZ. Ele nao e uma interface de rede: e uma entrada a mais na
# tabela de rota privada.
#
# Vale por dois motivos. O `loader` le os ~200 MB de Parquet do bucket `origem`
# a cada carga inicial, e o NAT cobra por GB trafegado: esse trafego sai de cima
# dele. E o acesso passa a ser interno a AWS, sem chegar a internet -- o mesmo
# dado, um salto a menos de exposicao.
resource "aws_vpc_endpoint" "s3" {
  count = var.create_network ? 1 : 0

  vpc_id            = aws_vpc.main[0].id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private[0].id]

  tags = {
    Name = "${local.name}-s3-endpoint"
  }
}
