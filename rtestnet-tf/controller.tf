resource "google_compute_address" "controller_ext_addr" {
  name = "${var.resources_name}-controller"
  address_type = "EXTERNAL"
}

resource "google_dns_record_set" "controller_dns_record" {
  name = "controller.${google_dns_managed_zone.dns_zone.dns_name}"
  managed_zone = "${google_dns_managed_zone.dns_zone.name}"
  type = "A"
  ttl = 300
  rrdatas = ["${google_compute_address.controller_ext_addr.address}"]
}

resource "google_compute_instance" "controller_host" {
  name = "${var.resources_name}-controller"
  machine_type = "n1-standard-1"
  tags = ["${var.resources_name}-controller"]
  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-1810"
    }
  }
  network_interface {
    subnetwork = "${google_compute_subnetwork.subnet.self_link}"
    access_config {
      nat_ip = "${google_compute_address.controller_ext_addr.address}"
    }
  }
}
