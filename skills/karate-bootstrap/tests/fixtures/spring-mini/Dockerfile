FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/shipments.jar app.jar
ENV JAVA_OPTS="-Xmx512m"
EXPOSE 8080
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
