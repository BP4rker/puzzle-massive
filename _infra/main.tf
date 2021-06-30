# TODO: split this out into multiple .tf files

terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

resource "digitalocean_project" "puzzle_massive" {
  name        = "Puzzle Massive - ${var.environment} ${var.project_version}"
  description = var.project_description
  purpose     = "Web Application"
  environment = var.project_environment
  resources   = [digitalocean_droplet.puzzle_massive.urn, digitalocean_spaces_bucket.cdn.urn, digitalocean_spaces_bucket.ephemeral_artifacts.urn]
}

resource "digitalocean_vpc" "puzzle_massive" {
  name        = "puzzle-massive-${lower(var.environment)}"
  description = "Puzzle Massive network for the ${var.environment} environment"
  region      = var.region
  ip_range    = var.vpc_ip_range
}

resource "digitalocean_tag" "fw_developer_ssh" {
  name = "fw_puzzle_massive_${lower(var.environment)}_developer_ssh"
}
resource "digitalocean_tag" "fw_web" {
  name = "fw_puzzle_massive_${lower(var.environment)}_web"
}

resource "digitalocean_firewall" "developer_ssh" {
  name = "puzzle-massive-${lower(var.environment)}-developer-ssh"
  tags = [digitalocean_tag.fw_developer_ssh.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.developer_ips
  }
  outbound_rule {
    protocol              = "tcp"
    port_range            = "22"
    destination_addresses = var.developer_ips
  }
}

resource "digitalocean_firewall" "web" {
  name = "puzzle-massive-${lower(var.environment)}-web"
  tags = [digitalocean_tag.fw_web.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = concat(var.web_ips, var.developer_ips)
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = concat(var.web_ips, var.developer_ips)
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "random_uuid" "ephemeral_artifacts" {
}
resource "digitalocean_spaces_bucket" "ephemeral_artifacts" {
  name   = substr("ephemeral-artifacts-${random_uuid.ephemeral_artifacts.result}", 0, 63)
  region = var.bucket_region
  acl    = "private"
  lifecycle_rule {
    enabled = true
    expiration {
      days = 26
    }
  }
}

resource "digitalocean_spaces_bucket_object" "add_dev_user_sh" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = "bin/add-dev-user.sh"
  acl    = "private"
  source = "../bin/add-dev-user.sh"
}
resource "digitalocean_spaces_bucket_object" "update_sshd_config_sh" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = "bin/update-sshd-config.sh"
  acl    = "private"
  source = "../bin/update-sshd-config.sh"
}
resource "digitalocean_spaces_bucket_object" "set_external_puzzle_massive_in_hosts_sh" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = "bin/set-external-puzzle-massive-in-hosts.sh"
  acl    = "private"
  source = "../bin/set-external-puzzle-massive-in-hosts.sh"
}
resource "digitalocean_spaces_bucket_object" "setup_sh" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = "bin/setup.sh"
  acl    = "private"
  source = "../bin/setup.sh"
}
resource "digitalocean_spaces_bucket_object" "iptables_setup_firewall_sh" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = "bin/iptables-setup-firewall.sh"
  acl    = "private"
  source = "../bin/iptables-setup-firewall.sh"
}
resource "digitalocean_spaces_bucket_object" "infra_development_build_sh" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = "bin/infra-development-build.sh"
  acl    = "private"
  source = "../bin/infra-development-build.sh"
}
resource "digitalocean_spaces_bucket_object" "infra_acceptance_build_sh" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = "bin/infra-acceptance-build.sh"
  acl    = "private"
  source = "../bin/infra-acceptance-build.sh"
}
resource "digitalocean_spaces_bucket_object" "artifact" {
  region = digitalocean_spaces_bucket.ephemeral_artifacts.region
  bucket = digitalocean_spaces_bucket.ephemeral_artifacts.name
  key    = var.artifact
  acl    = "private"
  source = "${lower(var.environment)}/${var.artifact}"
}

resource "local_file" "aws_credentials" {
  filename = "${lower(var.environment)}/aws_credentials"
  # Hint that this has been generated from a template and shouldn't be edited by the owner.
  file_permission = "0400"
  sensitive_content = templatefile("aws_credentials.tmpl", {
    do_spaces_access_key_id     = var.do_spaces_access_key_id
    do_spaces_secret_access_key = var.do_spaces_secret_access_key
  })
}

resource "local_file" "aws_config" {
  filename = "${lower(var.environment)}/aws_config"
  # Hint that this has been generated from a template and shouldn't be edited by the owner.
  file_permission = "0400"
  content = templatefile("aws_config.tmpl", {
    bucket_region = var.bucket_region
  })
}
