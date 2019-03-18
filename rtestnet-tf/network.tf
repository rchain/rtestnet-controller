resource "google_compute_network" "network" {
  name = "${var.resources_name}"
  auto_create_subnetworks = "false"
}

resource "google_compute_subnetwork" "subnet" {
  name = "${var.resources_name}"
  ip_cidr_range = "10.4.1.0/24"
  network = "${google_compute_network.network.self_link}"
}

resource "google_compute_firewall" "fw_public" {
  name = "${var.resources_name}-public-all"
  network = "${google_compute_network.network.self_link}"
  priority = 500
  allow {
    protocol = "icmp"
  }
  allow {
    protocol = "tcp"
    ports = [ 22 ]
  }
}

resource "google_compute_firewall" "fw_controller_node" {
  name = "${var.resources_name}-controller-node"
  network = "${google_compute_network.network.self_link}"
  priority = 510
  source_tags = [ "${var.resources_name}-controller" ]
  target_tags = [ "${var.resources_name}-node" ]
  allow {
    protocol = "all"
  }
}

resource "google_compute_firewall" "fw_node_controller" {
  name = "${var.resources_name}-node-controller"
  network = "${google_compute_network.network.self_link}"
  priority = 520
  source_tags = [ "${var.resources_name}-node" ]
  target_tags = [ "${var.resources_name}-controller" ]
  allow {
    protocol = "tcp"
    ports = [ 5555 ]
  }
}

resource "google_compute_firewall" "fw_public_node" {
  name = "${var.resources_name}-public-node"
  network = "${google_compute_network.network.self_link}"
  priority = 530
  target_tags = [ "${var.resources_name}-node" ]
  allow {
    protocol = "tcp"
    ports = [ 40400, 40404 ]
  }
}

resource "google_dns_managed_zone" "dns_zone" {
  provider = "google-beta"
  name = "${var.resources_name}"
  dns_name = "${var.resources_name}.rchain-dev.tk."
}
