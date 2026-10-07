# The shelf in AWS that holds the ingestion image (Step 2.7).

resource "aws_ecr_repository" "fetcher" {
  name = "${local.prefix}-fetcher"

  # A tag, once pushed, can never be moved to a different image.
  image_tag_mutability = "IMMUTABLE"

  # Check each pushed image for known security problems (free basic scan).
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Old images cost storage. Keep the five most recent and delete the rest.
resource "aws_ecr_lifecycle_policy" "fetcher" {
  repository = aws_ecr_repository.fetcher.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the 5 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

output "fetcher_repository_url" {
  value = aws_ecr_repository.fetcher.repository_url
}
