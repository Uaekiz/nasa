package com.pyrosphere.backend.service;

import com.pyrosphere.backend.dto.ApiModels.ComparisonResponse;
import com.pyrosphere.backend.dto.ApiModels.Difference;
import com.pyrosphere.backend.dto.ApiModels.DifferenceValue;
import com.pyrosphere.backend.dto.ApiModels.MeasurementView;
import com.pyrosphere.backend.dto.ApiModels.Series;
import com.pyrosphere.backend.dto.ApiModels.SeriesPoint;
import com.pyrosphere.backend.dto.ApiModels.SourceView;
import com.pyrosphere.backend.dto.ApiModels.WarningView;
import com.pyrosphere.backend.exception.ApiException;
import com.pyrosphere.backend.service.ExperimentService.ExperimentRow;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class ComparisonService {

    private final ExperimentService experimentService;
    private final CatalogService catalogService;

    public ComparisonService(ExperimentService experimentService,
                             CatalogService catalogService) {
        this.experimentService = experimentService;
        this.catalogService = catalogService;
    }

    private static final class Metric {
        private final String name;
        private final String unit;
        private final Map<String, SeriesPoint> points = new LinkedHashMap<>();

        private Metric(String name, String unit) {
            this.name = name;
            this.unit = unit;
        }
    }

    public ComparisonResponse compare(List<String> experimentIds) {
        if (experimentIds == null || experimentIds.size() < 2 || experimentIds.size() > 3) {
            throw ApiException.validation(
                    "Karşılaştırma için 2 veya 3 experimentId gönderilmelidir.",
                    List.of(Map.of("field", "experimentIds",
                            "issue", "size must be 2 or 3, received "
                                    + (experimentIds == null ? 0 : experimentIds.size()))));
        }
        Set<String> unique = new LinkedHashSet<>();
        for (String id : experimentIds) {
            if (id == null || id.isBlank()) {
                throw ApiException.validation("experimentId boş olamaz.",
                        List.of(Map.of("field", "experimentIds", "issue", "blank identifier")));
            }
            if (!unique.add(id)) {
                throw ApiException.validation("Aynı experimentId birden fazla gönderilemez.",
                        List.of(Map.of("field", "experimentIds", "issue", "duplicate " + id)));
            }
        }

        List<ExperimentRow> experiments = new ArrayList<>();
        for (String id : experimentIds) {
            experiments.add(experimentService.requireExperiment(id));
        }

        Map<String, Metric> metrics = new LinkedHashMap<>();
        Set<String> warningKeys = new LinkedHashSet<>();
        List<WarningView> warnings = new ArrayList<>();
        Set<String> sourceIds = new LinkedHashSet<>();

        for (ExperimentRow experiment : experiments) {
            if (experiment.sourceId() != null) {
                sourceIds.add(experiment.sourceId());
            }
            int measurementRows = 0;
            List<MeasurementView> rows = experimentService.measurements(
                    experiment.experimentId(), "MEASUREMENT");
            measurementRows = rows.size();
            for (MeasurementView measurement : rows) {
                boolean usable = "VERIFIED".equals(measurement.qualityStatus())
                        && measurement.value() != null;
                if (!usable) {
                    String key = experiment.experimentId() + "|" + measurement.name()
                            + "|" + measurement.qualityStatus();
                    if (warningKeys.add(key)) {
                        warnings.add(new WarningView(
                                "DATA_EXCLUDED",
                                experiment.experimentId() + " / " + measurement.name()
                                        + " sayısal karşılaştırmaya katılmadı. Durum: "
                                        + measurement.qualityStatus() + ", ham değer: '"
                                        + measurement.rawValue() + "'."));
                    }
                    continue;
                }
                String key = measurement.name() + "|" + measurement.unit();
                Metric metric = metrics.computeIfAbsent(key,
                        ignored -> new Metric(measurement.name(), measurement.unit()));
                metric.points.put(experiment.experimentId(),
                        new SeriesPoint(experiment.experimentId(), measurement.value(),
                                measurement.sourceId()));
                if (measurement.sourceId() != null) {
                    sourceIds.add(measurement.sourceId());
                }
            }
            if (measurementRows == 0) {
                String key = experiment.experimentId() + "|NO_NUMERIC_MEASUREMENTS";
                if (warningKeys.add(key)) {
                    warnings.add(new WarningView("NO_NUMERIC_MEASUREMENTS",
                            experiment.experimentId()
                                    + " kaynağında sayısal ölçüm yok; yalnızca koşullar mevcut."));
                }
            }
        }


        List<Series> series = new ArrayList<>();
        List<Difference> differences = new ArrayList<>();
        boolean comparable = false;

        for (Metric metric : metrics.values()) {
            List<SeriesPoint> points = new ArrayList<>(metric.points.values());
            if (points.isEmpty()) {
                continue;
            }
            series.add(new Series(metric.name, metric.unit, points));
            if (points.size() < 2) {
                continue;
            }
            comparable = true;
            double min = points.stream().mapToDouble(SeriesPoint::value).min().orElseThrow();
            double max = points.stream().mapToDouble(SeriesPoint::value).max().orElseThrow();
            List<DifferenceValue> values = points.stream()
                    .map(point -> new DifferenceValue(point.experimentId(), point.value()))
                    .toList();
            String unit = metric.unit == null ? "" : " " + metric.unit;
            double spread = BigDecimal.valueOf(max - min)
                    .setScale(6, RoundingMode.HALF_UP)
                    .stripTrailingZeros()
                    .doubleValue();
            String note = spread == 0d
                    ? "Tüm doğrulanmış değerler eşit."
                    : "Fark (max - min) = " + spread + unit + ".";
            differences.add(new Difference(metric.name, values, note));
        }

        String status;
        if (comparable) {
            status = "COMPARABLE";
        } else if (!series.isEmpty()) {
            status = "LIMITED";
        } else {
            status = "INSUFFICIENT_DATA";
        }

        List<SourceView> sources = catalogService.findSources(new ArrayList<>(sourceIds));
        return new ComparisonResponse(List.copyOf(experimentIds), status, differences,
                series, warnings, sources);
    }
}

