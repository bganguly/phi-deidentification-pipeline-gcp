variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "GKE cluster name"
  type        = string
  default     = "phi-pipeline"
}

variable "node_machine_type" {
  description = "GCE machine type for cluster nodes"
  type        = string
  default     = "n1-standard-4"
}
