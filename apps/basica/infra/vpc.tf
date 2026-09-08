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
  count = var.create_network ? length(var.public_subnet_cidrs) : 0

  vpc_id            = aws_vpc.main[0].id
  cidr_block        = var.public_subnet_cidrs[count.index]
  availability_zone = data.aws_availability_zones.available[0].names[count.index]

  # O bastion e o NAT precisam de IP publico. Ligar aqui evita repetir
  # `associate_public_ip_address` em cada recurso da sub-rede.
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name}-public-${count.index}"
    Tier = "public"
  }
}

# Privadas: instancias do Auto Scaling Group, tasks Fargate e o subnet group do
# RDS. Nada aqui tem endereco publico.
resource "aws_subnet" "private" {
  count = var.create_network ? length(var.private_subnet_cidrs) : 0

  vpc_id            = aws_vpc.main[0].id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = data.aws_availability_zones.available[0].names[count.index]

  tags = {
    Name = "${local.name}-private-${count.index}"
    Tier = "private"
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
