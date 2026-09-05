FROM golang:1.22 AS build
WORKDIR /src
COPY . .
RUN go build -o /app ./cmd/app

FROM alpine:3.20
SHELL ["/bin/sh", "-o", "pipefail", "-c"]
RUN apk add --no-cache curl
RUN curl -sSL https://example.com/install.sh | sh
COPY --from=build /app /app
USER 10001
ENTRYPOINT ["/app"]
