package com.pyrosphere.backend.controller;

import com.pyrosphere.backend.service.CatalogService;
import com.pyrosphere.backend.service.ComparisonService;
import com.pyrosphere.backend.service.ExperimentService;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Read-only real-DB fixtures for a browser test; no HTTP application is started. */
@SpringBootTest
class BrowserApiFixtureTests {
    @Autowired ExperimentService experiments;
    @Autowired CatalogService catalog;
    @Autowired ComparisonService comparisons;
    private final List<String> responses = new ArrayList<>();

    private void capture(MockMvc mvc, String path) throws Exception {
        String json = mvc.perform(get(URI.create(path))).andExpect(status().isOk()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        responses.add("{\"method\":\"GET\",\"path\":\"" + path + "\",\"body\":" + json + "}");
    }

    @Test
    void exportsActualCataloguePagesDetailsSourcesAndComparisonForBrowserChecks() throws Exception {
        var mvc = MockMvcBuilders.standaloneSetup(new ExperimentController(experiments),
                new InvestigationController(catalog), new SourceController(catalog),
                new ComparisonChatController(comparisons, null)).build();
        capture(mvc, "/api/v1/investigations");
        capture(mvc, "/api/v1/experiments?page=0&size=20");
        Set<String> detailIds = new LinkedHashSet<>();
        Set<String> sourceIds = new LinkedHashSet<>();
        for (String investigation : List.of("PSI-69", "PSI-25", "PSI-100", "PSI-101")) {
            capture(mvc, "/api/v1/experiments?page=0&size=20&investigationId=" + investigation);
            var page = experiments.list(investigation, null, 0, 20);
            page.items().stream().limit(2).forEach(item -> detailIds.add(item.experimentId()));
        }
        capture(mvc, "/api/v1/experiments?page=1&size=20&investigationId=PSI-69");
        boolean missingFound = false, rodFound = false;
        for (int page = 0; page < 3 && !missingFound; page++) {
            for (var item : experiments.list("PSI-69", null, page, 100).items()) {
                var detail = experiments.detail(item.experimentId());
                if (detail.conditions().stream().anyMatch(value -> value.name().equals("Droplet initial diameter") && value.qualityStatus().equals("MISSING"))) {
                    detailIds.add(detail.experimentId());
                    missingFound = true;
                    break;
                }
            }
        }
        for (int page = 0; page < 2 && !rodFound; page++) {
            for (var item : experiments.list("PSI-25", null, page, 100).items()) {
                if (item.fuel() != null && item.fuel().toLowerCase().contains("rod")) {
                    detailIds.add(item.experimentId());
                    rodFound = true;
                    break;
                }
            }
        }
        assertTrue(missingFound);
        assertTrue(rodFound);
        for (String id : detailIds) {
            capture(mvc, "/api/v1/experiments/" + URLEncoder.encode(id, StandardCharsets.UTF_8));
            experiments.detail(id).sources().forEach(source -> sourceIds.add(source.sourceId()));
        }
        for (String id : sourceIds) capture(mvc, "/api/v1/sources/" + URLEncoder.encode(id, StandardCharsets.UTF_8));
        var flex = experiments.list("PSI-69", null, 0, 2).items();
        String body = "{\"experimentIds\":[\"" + flex.get(0).experimentId() + "\",\"" + flex.get(1).experimentId() + "\"]}";
        String comparison = mvc.perform(post("/api/v1/comparisons").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        responses.add("{\"method\":\"POST\",\"path\":\"/api/v1/comparisons\",\"body\":" + comparison + "}");
        Files.writeString(Path.of("target/flamescope-browser-api.json"), "{\"responses\":[" + String.join(",", responses) + "]}", StandardCharsets.UTF_8);
    }
}
