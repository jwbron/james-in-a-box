# Build stage
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the binary
RUN CGO_ENABLED=0 GOOS=linux go build -o github-mcp .

# Runtime stage
FROM alpine:3.19

RUN apk --no-cache add ca-certificates

WORKDIR /app

# Copy the binary from builder
COPY --from=builder /app/github-mcp .

# Default to HTTP mode for Cloud Run
ENV PORT=8080
EXPOSE 8080

# Run in HTTP mode
ENTRYPOINT ["/app/github-mcp"]
CMD ["--http", ":8080"]
