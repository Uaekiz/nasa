package com.pyrosphere.backend.dto;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * API contract v1 response/request payloads. Names are serialized as-is
 * (camelCase), matching docs/api-contract-v1.md.
 */
public final class ApiModels {

    private ApiModels() {
    }

    public record MeasurementView(
            String name,
            Double value,
            String unit,
            String qualifier,
            Double startValue,
            Double endValue,
            Double minValue,
            Double maxValue,
            String rawValue,
            String missingReason,
            String qualityStatus,
            String sourceId) {
    }

    public record FindingView(
            String name,
            String value,
            String rawValue,
            String sourceId) {
    }

    public record WarningView(String code, String message) {
    }

    public record SourceView(
            String sourceId,
            String title,
            String sourceType,
            String investigationId,
            String doi,
            String originalUrl,
            String documentUrl) {
    }

    public record ExperimentSummary(
            String experimentId,
            String investigationId,
            String sourceTestId,
            String fuel,
            LocalDate date,
            String reportedOutcome) {
    }

    public record ExperimentPage(
            List<ExperimentSummary> items,
            int page,
            int size,
            long totalElements,
            int totalPages) {
    }

    public record ExperimentDetail(
            String experimentId,
            String investigationId,
            String sourceTestId,
            String experimentIdentifier,
            String fuel,
            LocalDate date,
            String dateRaw,
            String testTime,
            String reportedOutcome,
            List<MeasurementView> conditions,
            List<MeasurementView> measurements,
            List<FindingView> reportedFindings,
            List<SourceView> sources,
            List<WarningView> warnings) {
    }

    public record InvestigationView(
            String investigationId,
            String name,
            String description,
            List<String> availableDataTypes) {
    }

    public record InvestigationList(List<InvestigationView> items) {
    }

    public record ComparisonRequest(List<String> experimentIds) {
    }

    public record DifferenceValue(String experimentId, Double value) {
    }

    public record Difference(String field, List<DifferenceValue> values, String note) {
    }

    public record SeriesPoint(String experimentId, Double value, String sourceId) {
    }

    public record Series(String metric, String unit, List<SeriesPoint> points) {
    }

    public record ComparisonResponse(
            List<String> experimentIds,
            String status,
            List<Difference> differences,
            List<Series> series,
            List<WarningView> warnings,
            List<SourceView> sources) {
    }

    public record ChatRequest(
            String question,
            List<String> investigationIds,
            List<String> experimentIds,
            String language) {
    }

    public record ErrorBody(String code, String message, List<Map<String, Object>> details) {
    }

    public record ErrorResponse(String requestId, ErrorBody error) {
    }
}
