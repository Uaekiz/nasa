package com.pyrosphere.backend.config;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class RagClientConfig {

    @Bean
    public RestClient ragRestClient(
            @Value("${pyrosphere.rag-service-url:http://localhost:8000}") String ragServiceUrl,
            @Value("${pyrosphere.rag-timeout-seconds:120}") long timeoutSeconds) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(5));
        requestFactory.setReadTimeout(Duration.ofSeconds(timeoutSeconds));
        return RestClient.builder()
                .baseUrl(ragServiceUrl)
                .requestFactory(requestFactory)
                .build();
    }
}
