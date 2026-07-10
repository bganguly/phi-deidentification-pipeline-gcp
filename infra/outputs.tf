output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.phi_pipeline.name
}

output "cluster_endpoint" {
  description = "GKE cluster API server endpoint"
  value       = google_container_cluster.phi_pipeline.endpoint
  sensitive   = true
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value = join(" ", [
    "gcloud container clusters get-credentials",
    google_container_cluster.phi_pipeline.name,
    "--region", var.region,
    "--project", var.project_id,
  ])
}
