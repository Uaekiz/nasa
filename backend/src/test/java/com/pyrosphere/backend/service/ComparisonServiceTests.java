package com.pyrosphere.backend.service;

import com.pyrosphere.backend.dto.ApiModels.MeasurementView;
import com.pyrosphere.backend.exception.ApiException;
import com.pyrosphere.backend.service.ExperimentService.ExperimentRow;
import java.util.List;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ComparisonServiceTests {
    private static final String SOURCE = "PSI-69:experimental-table:v1";
    private static class FakeExperiments extends ExperimentService {
        private final Map<String, ExperimentRow> rows = new HashMap<>();
        private final Map<String, List<MeasurementView>> measurements = new HashMap<>();
        private int queries = 0;

        FakeExperiments() { super(null, null); }

        @Override
        public ExperimentRow requireExperiment(String id) { queries++; return rows.get(id); }

        @Override
        public List<MeasurementView> measurements(String id, String category) {
            queries++;
            assertEquals("MEASUREMENT", category);
            return measurements.get(id);
        }
    }

    private static class FakeCatalog extends CatalogService {
        FakeCatalog() { super(null); }

        @Override
        public List<com.pyrosphere.backend.dto.ApiModels.SourceView> findSources(List<String> ids) {
            assertTrue(ids.stream().allMatch(SOURCE::equals));
            return List.of();
        }
    }

    private final FakeExperiments experiments = new FakeExperiments();
    private final CatalogService catalog = new FakeCatalog();
    private final ComparisonService service = new ComparisonService(experiments, catalog);

    private MeasurementView measurement(String name, Double value, String unit, String quality) {
        return new MeasurementView(name, value, unit, value == null ? "UNKNOWN" : "EXACT",
                null, null, null, null, value == null ? "" : value.toString(),
                value == null ? "EMPTY_CELL" : null, quality, SOURCE);
    }

    private void experiment(String id, List<MeasurementView> measurements) {
        experiments.rows.put(id, new ExperimentRow(id, "PSI-69",
                SOURCE, "source-test", null, "Methanol", null, null, null, "Disruption"));
        experiments.measurements.put(id, measurements);
    }

    @Test
    void ambiguousBurningRateAndMissingValuesNeverEnterSeries() {
        String first = "PSI-69:run-0001";
        String second = "PSI-69:run-0002";
        experiment(first, List.of(measurement("Burning rate", .52, "mm", "REQUIRES_REVIEW"),
                measurement("Burn time", 4.37, "s", "VERIFIED")));
        experiment(second, List.of(measurement("Burning rate", .61, "mm", "REQUIRES_REVIEW"),
                measurement("Burn time", null, "s", "MISSING")));
        var response = service.compare(List.of(first, second));
        assertEquals("LIMITED", response.status());
        assertEquals(1, response.series().size());
        var series = response.series().getFirst();
        assertEquals("Burn time", series.metric());
        assertEquals("s", series.unit());
        assertEquals(1, series.points().size());
        assertEquals(first, series.points().getFirst().experimentId());
        assertEquals(SOURCE, series.points().getFirst().sourceId());
        assertEquals(4.37, series.points().getFirst().value());
        assertTrue(response.differences().isEmpty());
        assertEquals(3, response.warnings().size());
    }

    @Test
    void realMetricAndExperimentIdsDefineSeriesAndDifferences() {
        String first = "PSI-69:run-0001";
        String second = "PSI-69:run-0002";
        experiment(first, List.of(measurement("Burn time", 4.37, "s", "VERIFIED")));
        experiment(second, List.of(measurement("Burn time", 6.5, "s", "VERIFIED")));
        var response = service.compare(List.of(first, second));
        assertEquals("COMPARABLE", response.status());
        assertEquals(List.of(first, second), response.experimentIds());
        assertEquals("Burn time", response.differences().getFirst().field());
        assertEquals(List.of(4.37, 6.5), response.series().getFirst().points().stream().map(p -> p.value()).toList());
        assertTrue(response.differences().getFirst().note().contains("2.13"));
    }

    @Test
    void noUsableMeasurementsAreReportedAsInsufficient() {
        experiment("a", List.of(measurement("Burn time", null, "s", "MISSING")));
        experiment("b", List.of(measurement("Burning rate", .52, "mm", "REQUIRES_REVIEW")));
        var response = service.compare(List.of("a", "b"));
        assertEquals("INSUFFICIENT_DATA", response.status());
        assertTrue(response.series().isEmpty());
        assertFalse(response.warnings().isEmpty());
    }

    @Test
    void invalidOrDuplicateSelectionsAreRejectedBeforeQuerying() {
        assertThrows(ApiException.class, () -> service.compare(List.of()));
        assertThrows(ApiException.class, () -> service.compare(List.of("a", "a")));
        assertEquals(0, experiments.queries);
    }

    @Test
    void sourceThresholdIsNotComparedAsAnExactNumber() {
        var threshold = new MeasurementView("Final CO", 500d, "ppm", "GREATER_THAN", null, null, null, null,
                ">500", null, "VERIFIED", "PSI-25:experimental-table:v1");
        experiment("a", List.of(threshold));
        experiment("b", List.of(measurement("Final CO", 300d, "ppm", "VERIFIED")));
        var response = service.compare(List.of("a", "b"));
        assertEquals("LIMITED", response.status());
        assertEquals(1, response.series().getFirst().points().size());
        assertEquals("b", response.series().getFirst().points().getFirst().experimentId());
        assertFalse(response.warnings().isEmpty());
    }
}
