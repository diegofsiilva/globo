provider "aws" {
  region = var.region

  # A conta e compartilhada com outros projetos. Estas tags sao o que permite
  # separar custo e responsabilidade no Cost Explorer depois.
  default_tags {
    tags = {
      Project     = "argus"
      Component   = "ingestao-eventos"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = "inteli/t15/g04"
    }
  }
}
