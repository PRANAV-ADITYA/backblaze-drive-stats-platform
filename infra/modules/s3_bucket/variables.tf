variable "name" {
  description = "Full, globally unique bucket name."
  type        = string
}

variable "versioning" {
  description = "Keep old copies of overwritten or deleted objects (old copies expire after 30 days)."
  type        = bool
  default     = false
}

variable "glacier_ir_after_days" {
  description = "Move objects to S3 Glacier Instant Retrieval after this many days. null = never."
  type        = number
  default     = null
}
