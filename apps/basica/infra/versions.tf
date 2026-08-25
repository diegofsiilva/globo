terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Faixa fechada no major: 6.x traz breaking changes que a gente nao quer
      # herdar num terraform init de outra maquina.
      version = "~> 5.60"
    }

    # Gera a senha do RDS quando ela vem do Secrets Manager.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
