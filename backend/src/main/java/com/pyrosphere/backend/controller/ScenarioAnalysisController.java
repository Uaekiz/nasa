package com.pyrosphere.backend.controller;

import com.pyrosphere.backend.exception.ApiException;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.net.SocketTimeoutException;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping("/api/v1/scenario-analyses")
public class ScenarioAnalysisController {
    private final RestClient ragRestClient;

    public ScenarioAnalysisController(RestClient ragRestClient) {
        this.ragRestClient = ragRestClient;
    }

    public record ScenarioParams(
            @NotNull(message = "Oxygen is required.") @DecimalMin(value = "0", message = "Oxygen must be at least 0.") @DecimalMax(value = "100", message = "Oxygen must not exceed 100.") Double oxygenPercent,
            @NotNull(message = "Pressure is required.") @DecimalMin(value = "0", inclusive = false, message = "Pressure must be greater than 0.") Double pressureKpa,
            @NotNull(message = "Airflow is required.") @DecimalMin(value = "0", message = "Airflow must not be negative.") Double airflowCmS,
            @NotNull(message = "Gravity is required.") @DecimalMin(value = "0", message = "Gravity must not be negative.") Double gravityG,
            @NotNull(message = "Temperature is required.") @DecimalMin(value = "-273.15", message = "Temperature must be at least -273.15 C.") Double temperatureC,
            @NotNull(message = "Ignition power is required.") @DecimalMin(value = "0", message = "Ignition power must not be negative.") Double ignitionPowerW,
            @NotBlank(message = "Material is required.") @Size(max = 120, message = "Material must not exceed 120 characters.") String material,
            @NotBlank(message = "Flow direction is required.") @Pattern(regexp = "CONCURRENT|OPPOSED", message = "Flow direction must be CONCURRENT or OPPOSED.") String flowDirection,
            @NotNull(message = "CO is required.") @DecimalMin(value = "0", message = "CO must not be negative.") Double coPpm,
            @NotNull(message = "CO2 is required.") @DecimalMin(value = "0", message = "CO2 must not be negative.") @DecimalMax(value = "100", message = "CO2 must not exceed 100.") Double co2Percent,
            @Pattern(regexp = "INITIAL|FINAL|UNSPECIFIED", message = "CO phase must be INITIAL, FINAL or UNSPECIFIED.") String coMeasurementPhase,
            @Pattern(regexp = "INITIAL|FINAL|UNSPECIFIED", message = "CO2 phase must be INITIAL, FINAL or UNSPECIFIED.") String co2MeasurementPhase
    ) {
        public ScenarioParams {
            for (Double value : new Double[] {oxygenPercent, pressureKpa, airflowCmS,
                    gravityG, temperatureC, ignitionPowerW, coPpm, co2Percent}) {
                if (value != null && !Double.isFinite(value)) {
                    throw new IllegalArgumentException("Scenario numeric inputs must be finite.");
                }
            }
            material = material == null ? null : material.trim();
            coMeasurementPhase = coMeasurementPhase == null ? "UNSPECIFIED" : coMeasurementPhase;
            co2MeasurementPhase = co2MeasurementPhase == null ? "UNSPECIFIED" : co2MeasurementPhase;
        }

        @JsonAnySetter
        public void rejectUnknownParameter(String name, Object value) {
            throw new IllegalArgumentException("Unsupported scenario parameter: " + name);
        }
    }

    public record ScenarioRequest(@NotNull(message = "Capture time is required.") Instant capturedAt,
                                  @NotNull(message = "Scenario inputs are required.") @Valid ScenarioParams params) {}

    public record ScenarioResponse(String requestId, String status, Instant capturedAt,
                                   ScenarioParams params, Map<String, Object> evidence) {}

    @PostMapping
    public ScenarioResponse receive(@Valid @RequestBody ScenarioRequest request) {
        Map<String, Object> evidence;
        try {
            // The local screenshot is deliberately not sent to a text/vision model.
            evidence = ragRestClient.post().uri("/rag/v1/scenarios/evidence")
                    .body(Map.of("material", request.params().material(), "params", request.params()))
                    .retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() {});
        } catch (RestClientResponseException exception) {
            if (exception.getStatusCode().value() == 504) {
                throw new ApiException(HttpStatus.GATEWAY_TIMEOUT, "RAG_TIMEOUT",
                        "The scenario source service timed out. The saved inputs and image remain available.");
            }
            if (exception.getStatusCode().value() == 400) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR",
                        "The scenario source service rejected the supplied inputs.");
            }
            throw unavailable("Scenario sources could not be retrieved from the RAG service.");
        } catch (RestClientException exception) {
            for (Throwable cause = exception; cause != null; cause = cause.getCause()) {
                if (cause instanceof SocketTimeoutException) {
                    throw new ApiException(HttpStatus.GATEWAY_TIMEOUT, "RAG_TIMEOUT",
                            "The scenario source connection timed out. Retry the saved scenario.");
                }
            }
            throw unavailable("The scenario source service could not be reached.");
        }
        if (evidence == null || !(evidence.get("sources") instanceof List<?>)
                || !List.of("EVIDENCE_FOUND", "INSUFFICIENT_EVIDENCE").contains(evidence.get("status"))) {
            throw unavailable("The scenario source service returned an empty or invalid response.");
        }
        return new ScenarioResponse(UUID.randomUUID().toString(), "EVIDENCE_RETRIEVED",
                request.capturedAt(), request.params(), evidence);
    }

    private static ApiException unavailable(String message) {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "RAG_UNAVAILABLE", message);
    }
}
