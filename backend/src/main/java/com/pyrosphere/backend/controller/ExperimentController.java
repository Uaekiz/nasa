package com.pyrosphere.backend.controller;

import com.pyrosphere.backend.dto.ApiModels.ExperimentDetail;
import com.pyrosphere.backend.dto.ApiModels.ExperimentPage;
import com.pyrosphere.backend.exception.ApiException;
import com.pyrosphere.backend.service.ExperimentService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class ExperimentController {

    /** Only these query parameters are part of contract v1. */
    private static final Set<String> ALLOWED_FILTERS =
            Set.of("investigationId", "fuel", "page", "size");

    private final ExperimentService experimentService;

    public ExperimentController(ExperimentService experimentService) {
        this.experimentService = experimentService;
    }

    @GetMapping("/experiments")
    public ExperimentPage experiments(
            @RequestParam(required = false) String investigationId,
            @RequestParam(required = false) String fuel,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            HttpServletRequest request) {
        rejectUnknownParameters(request);
        return experimentService.list(investigationId, fuel, page, size);
    }

    @GetMapping("/experiments/{experimentId}")
    public ExperimentDetail experiment(@PathVariable String experimentId) {
        return experimentService.detail(experimentId);
    }

    /**
     * Unsupported filters must not be ignored silently (contract section 5).
     */
    private static void rejectUnknownParameters(HttpServletRequest request) {
        List<Map<String, Object>> details = request.getParameterMap().keySet().stream()
                .filter(name -> !ALLOWED_FILTERS.contains(name))
                .map(name -> {
                    Map<String, Object> detail = new LinkedHashMap<>();
                    detail.put("field", name);
                    detail.put("issue", "unsupported query parameter");
                    return detail;
                })
                .toList();
        if (!details.isEmpty()) {
            throw ApiException.validation(
                    "An unsupported query parameter was supplied.", details);
        }
    }
}
