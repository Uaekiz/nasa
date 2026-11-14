package com.pyrosphere.backend.service;

import com.pyrosphere.backend.dto.ApiModels.ExperimentDetail;
import com.pyrosphere.backend.dto.ApiModels.ExperimentPage;
import com.pyrosphere.backend.dto.ApiModels.ExperimentSummary;
import com.pyrosphere.backend.dto.ApiModels.FindingView;
import com.pyrosphere.backend.dto.ApiModels.MeasurementView;
import com.pyrosphere.backend.dto.ApiModels.SourceView;
import com.pyrosphere.backend.dto.ApiModels.WarningView;
import com.pyrosphere.backend.exception.ApiException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class ExperimentService {

    private final JdbcClient jdbc;
    private final CatalogService catalogService;

    public ExperimentService(JdbcClient jdbc, CatalogService catalogService) {
        this.jdbc = jdbc;
        this.catalogService = catalogService;
    }

    public record ExperimentRow(
            String experimentId,
            String investigationId,
            String sourceId,
            String sourceTestId,
            String experimentIdentifier,
            String fuel,
            LocalDate date,
            String dateRaw,
            String testTime,
            String reportedOutcome) {
    }

    public ExperimentPage list(String investigationId, String fuel, int page, int size) {
        if (page < 0) {
            throw ApiException.validation("page 0 veya daha büyük olmalıdır.",
                    List.of(Map.of("field", "page", "issue", "must be >= 0")));
        }
        if (size < 1 || size > 100) {
            throw ApiException.validation("size 1 ile 100 arasında olmalıdır.",
                    List.of(Map.of("field", "size", "issue", "must be between 1 and 100")));
        }

        StringBuilder where = new StringBuilder(" WHERE 1 = 1");
        Map<String, Object> params = new LinkedHashMap<>();
        if (StringUtils.hasText(investigationId)) {
            catalogService.requireInvestigation(investigationId.trim());
            where.append(" AND investigation_id = :investigationId");
            params.put("investigationId", investigationId.trim());
        }
        if (StringUtils.hasText(fuel)) {
            where.append(" AND fuel = :fuel");
            params.put("fuel", fuel.trim());
        }

        long totalElements = jdbc.sql("SELECT count(*) FROM core.experiments" + where)
                .params(params)
                .query(Long.class)
                .single();

        List<ExperimentSummary> items = jdbc.sql("""
                        SELECT experiment_id, investigation_id, source_test_id, fuel,
                               experiment_date, reported_outcome
                        FROM core.experiments
                        """ + where + " ORDER BY experiment_id ASC LIMIT :limit OFFSET :offset")
                .params(params)
                .param("limit", size)
                .param("offset", (long) page * size)
                .query((rs, rowNum) -> new ExperimentSummary(
                        rs.getString("experiment_id"),
                        rs.getString("investigation_id"),
                        rs.getString("source_test_id"),
                        rs.getString("fuel"),
                        rs.getObject("experiment_date", LocalDate.class),
                        rs.getString("reported_outcome")))
                .list();

        int totalPages = totalElements == 0 ? 0 : (int) Math.ceil((double) totalElements / size);
        return new ExperimentPage(items, page, size, totalElements, totalPages);
    }

    public ExperimentRow requireExperiment(String experimentId) {
        return jdbc.sql("""
                        SELECT experiment_id, investigation_id, source_id, source_test_id,
                               experiment_identifier, fuel, experiment_date, date_raw,
                               test_time, reported_outcome
                        FROM core.experiments
                        WHERE experiment_id = :experimentId
                        """)
                .param("experimentId", experimentId)
                .query((rs, rowNum) -> new ExperimentRow(
                        rs.getString("experiment_id"),
                        rs.getString("investigation_id"),
                        rs.getString("source_id"),
                        rs.getString("source_test_id"),
                        rs.getString("experiment_identifier"),
                        rs.getString("fuel"),
                        rs.getObject("experiment_date", LocalDate.class),
                        rs.getString("date_raw"),
                        rs.getString("test_time"),
                        rs.getString("reported_outcome")))
                .optional()
                .orElseThrow(() -> ApiException.notFound("EXPERIMENT_NOT_FOUND",
                        "İstenen test bulunamadı: " + experimentId));
    }

    public ExperimentDetail detail(String experimentId) {
        ExperimentRow experiment = requireExperiment(experimentId);
        List<MeasurementView> conditions = measurements(experimentId, "CONDITION");
        List<MeasurementView> measurements = measurements(experimentId, "MEASUREMENT");

        List<FindingView> findings = jdbc.sql("""
                        SELECT name, value, raw_value, source_id
                        FROM core.reported_findings
                        WHERE experiment_id = :experimentId
                        ORDER BY display_order, finding_id
                        """)
                .param("experimentId", experimentId)
                .query((rs, rowNum) -> new FindingView(
                        rs.getString("name"),
                        rs.getString("value"),
                        rs.getString("raw_value"),
                        rs.getString("source_id")))
                .list();

        List<WarningView> warnings = warnings(experimentId);

        Set<String> sourceIds = new LinkedHashSet<>();
        if (experiment.sourceId() != null) {
            sourceIds.add(experiment.sourceId());
        }
        conditions.forEach(item -> addIfPresent(sourceIds, item.sourceId()));
        measurements.forEach(item -> addIfPresent(sourceIds, item.sourceId()));
        findings.forEach(item -> addIfPresent(sourceIds, item.sourceId()));
        List<SourceView> sources = catalogService.findSources(new ArrayList<>(sourceIds));

        return new ExperimentDetail(
                experiment.experimentId(),
                experiment.investigationId(),
                experiment.sourceTestId(),
                experiment.experimentIdentifier(),
                experiment.fuel(),
                experiment.date(),
                experiment.dateRaw(),
                experiment.testTime(),
                experiment.reportedOutcome(),
                conditions,
                measurements,
                findings,
                sources,
                warnings);
    }


    public List<MeasurementView> measurements(String experimentId, String category) {
        return jdbc.sql("""
                        SELECT name, value, unit, qualifier, start_value, end_value,
                               min_value, max_value, raw_value, missing_reason,
                               quality_status, source_id
                        FROM core.experiment_measurements
                        WHERE experiment_id = :experimentId AND category = :category
                        ORDER BY display_order, measurement_id
                        """)
                .param("experimentId", experimentId)
                .param("category", category)
                .query((rs, rowNum) -> new MeasurementView(
                        rs.getString("name"),
                        rs.getObject("value", Double.class),
                        rs.getString("unit"),
                        rs.getString("qualifier"),
                        rs.getObject("start_value", Double.class),
                        rs.getObject("end_value", Double.class),
                        rs.getObject("min_value", Double.class),
                        rs.getObject("max_value", Double.class),
                        rs.getString("raw_value"),
                        rs.getString("missing_reason"),
                        rs.getString("quality_status"),
                        rs.getString("source_id")))
                .list();
    }

    public List<WarningView> warnings(String experimentId) {
        return jdbc.sql("""
                        SELECT code, message
                        FROM core.experiment_warnings
                        WHERE experiment_id = :experimentId
                        ORDER BY warning_id
                        """)
                .param("experimentId", experimentId)
                .query((rs, rowNum) -> new WarningView(
                        rs.getString("code"),
                        rs.getString("message")))
                .list();
    }

    private static void addIfPresent(Set<String> values, String value) {
        if (value != null && !value.isBlank()) {
            values.add(value);
        }
    }
}

