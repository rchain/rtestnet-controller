variable "resources_name" { default = "rtestnet1" }
variable "gcp_zone" { default = "us-central1-a" }

provider "google" {
  project = "developer-222401"
  zone    = "${var.gcp_zone}"
}

provider "google-beta" {
  project = "developer-222401"
  zone    = "${var.gcp_zone}"
}
