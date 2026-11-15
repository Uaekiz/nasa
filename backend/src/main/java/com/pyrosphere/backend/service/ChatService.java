package com.pyrosphere.backend.service;

import com.pyrosphere.backend.dto.ApiModels.ChatRequest;
import com.pyrosphere.backend.dto.ApiModels.MeasurementView;
import com.pyrosphere.backend.exception.ApiException;
import com.pyrosphere.backend.service.ExperimentService.ExperimentRow;
import java.net.SocketTimeoutException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

/**
 * Coordinates POST /api/v1/chat with the FastAPI RAG service.
 * The browser never talks to the RAG service directly.
 */
@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);
    private static final int MAX_QUESTION_LENGTH = 4000;

    private final RestClient ragRestClient;
    private final ExperimentService experimentService;

    public ChatService(RestClient ragRestClient, ExperimentService experimentService) {
        this.ragRestClient = ragRestClient;
        this.experimentService = experimentService;
    }

    public Map<String, Object> capabilities() {
        try {
            Map<?, ?> response = ragRestClient.get().uri("/rag/v1/capabilities").retrieve().body(Map.class);
            if (response == null) {
                throw new IllegalStateException("Empty capabilities response");
            }
            Map<String, Object> result = new LinkedHashMap<>();
            response.forEach((key, value) -> result.put(String.valueOf(key), value));
            return result;
        } catch (Exception exception) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "RAG_UNAVAILABLE",
                    "RAG source scope is unavailable. Check the RAG service and pending service restarts.");
        }
    }

    public Map<String, Object> chat(ChatRequest request) {
        String question = request.question();
        if (question == null || question.isBlank()) {
            throw ApiException.validation("question zorunludur.",
                    List.of(Map.of("field", "question", "issue", "must not be blank")));
        }
        question = question.trim();
        if (question.length() > MAX_QUESTION_LENGTH) {
            throw ApiException.validation("question en fazla 4000 karakter olabilir.",
                    List.of(Map.of("field", "question",
                            "issue", "length must be <= " + MAX_QUESTION_LENGTH)));
        }

        String language = request.language() == null ? "en" : request.language();
        if (!"tr".equals(language) && !"en".equals(language)) {
            throw ApiException.validation("language yalnızca tr veya en olabilir.",
                    List.of(Map.of("field", "language", "issue", "must be tr or en")));
        }

        List<String> investigationIds = safeList(request.investigationIds());
        List<String> experimentIds = safeList(request.experimentIds());

        // Experiment ids must belong to the requested investigations when both are present.
        if (!investigationIds.isEmpty() && !experimentIds.isEmpty()) {
            for (String experimentId : experimentIds) {
                ExperimentRow row = experimentService.requireExperiment(experimentId);
                if (!investigationIds.contains(row.investigationId())) {
                    throw ApiException.validation(
                            "experimentId belirtilen araştırmaya ait değil: " + experimentId,
                            List.of(Map.of("field", "experimentIds",
                                    "issue", "not part of " + investigationIds)));
                }
            }
        }

        String requestId = UUID.randomUUID().toString();
        Map<String, Object> analysisContext = buildAnalysisContext(experimentIds);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("requestId", requestId);
        payload.put("question", question);
        payload.put("investigationIds", investigationIds);
        payload.put("experimentIds", experimentIds);
        payload.put("language", language);
        payload.put("analysisContext", analysisContext);

        return callRag(requestId, payload);
    }

    private Map<String, Object> callRag(String requestId, Map<String, Object> payload) {
        try {
            Map<?, ?> response = ragRestClient.post()
                    .uri("/rag/v1/answer")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(payload)
                    .retrieve()
                    .body(Map.class);

            if (response == null) {
                throw new ApiException(HttpStatus.BAD_GATEWAY, "RAG_UNAVAILABLE",
                        "RAG servisi boş yanıt döndürdü.");
            }
            Map<String, Object> result = new LinkedHashMap<>();
            response.forEach((key, value) -> result.put(String.valueOf(key), value));
            result.put("requestId", requestId);
            return result;
        } catch (ApiException exception) {
            throw exception;
        } catch (ResourceAccessException exception) {
            if (isTimeout(exception)) {
                log.warn("RAG isteği zaman aşımına uğradı (requestId={})", requestId);
                throw new ApiException(HttpStatus.GATEWAY_TIMEOUT, "RAG_TIMEOUT",
                        "RAG servisi zamanında yanıt vermedi.");
            }
            log.warn("RAG servisine ulaşılamadı (requestId={}): {}", requestId,
                    exception.getMessage());
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "RAG_UNAVAILABLE",
                    "RAG servisi şu anda kullanılamıyor.");
        } catch (Exception exception) {
            log.error("RAG isteği başarısız (requestId={})", requestId, exception);
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "RAG_UNAVAILABLE",
                    "RAG servisi şu anda kullanılamıyor.");
        }
    }

    /**
     * Builds a verified fact set from the database. Only VERIFIED numeric
     * measurements with a non-null value are included; everything else is
     * reported as a warning, never silently used.
     */
    private Map<String, Object> buildAnalysisContext(List<String> experimentIds) {
        if (experimentIds.isEmpty()) {
            return null;
        }
        List<Map<String, Object>> facts = new ArrayList<>();
        Set<Map<String, Object>> warnings = new LinkedHashSet<>();
        Set<String> sourceIds = new LinkedHashSet<>();

        for (String experimentId : experimentIds) {
            for (MeasurementView measurement : experimentService.measurements(
                    experimentId, "MEASUREMENT")) {
                if ("VERIFIED".equals(measurement.qualityStatus()) && measurement.value() != null
                        && ("EXACT".equals(measurement.qualifier()) || "APPROXIMATE".equals(measurement.qualifier()))) {
                    Map<String, Object> fact = new LinkedHashMap<>();
                    fact.put("name", measurement.name());
                    fact.put("value", measurement.value());
                    fact.put("unit", measurement.unit());
                    fact.put("experimentId", experimentId);
                    fact.put("sourceId", measurement.sourceId());
                    facts.add(fact);
                    if (measurement.sourceId() != null) {
                        sourceIds.add(measurement.sourceId());
                    }
                } else {
                    Map<String, Object> warning = new LinkedHashMap<>();
                    warning.put("code", "DATA_EXCLUDED");
                    warning.put("message", experimentId + " / " + measurement.name()
                            + " doğrulanmış sayısal değer olmadığı için bağlama alınmadı.");
                    warnings.add(warning);
                }
            }
        }
        if (facts.isEmpty() && warnings.isEmpty()) {
            return null;
        }

        Map<String, Object> context = new LinkedHashMap<>();
        context.put("task", "NUMERIC_SUMMARY");
        context.put("experimentIds", experimentIds);
        context.put("facts", facts);
        context.put("warnings", new ArrayList<>(warnings));
        context.put("sources", new ArrayList<>(sourceIds));
        return context;
    }

    private static boolean isTimeout(ResourceAccessException exception) {
        Throwable cause = exception.getCause();
        while (cause != null) {
            if (cause instanceof SocketTimeoutException) {
                return true;
            }
            cause = cause.getCause();
        }
        return false;
    }

    private static List<String> safeList(List<String> values) {
        if (values == null) {
            return List.of();
        }
        return values.stream()
                .filter(value -> value != null && !value.isBlank())
                .map(String::trim)
                .toList();
    }
}

