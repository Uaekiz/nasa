package com.pyrosphere.backend.service;

import com.pyrosphere.backend.controller.ExperimentController;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Read-only checks against the imported local source records. No HTTP server. */
@SpringBootTest
class ExperimentDatesTests {
    @Autowired ExperimentService experiments;

    @Test
    void partialSameDatesSurviveListDetailAndSerializedDtoWithoutYear() throws Exception {
        var page = experiments.list("PSI-101", null, 0, 20);
        assertEquals(109, page.totalElements());
        for (var expected : new String[][] {{"51", "21-Jul"}, {"51a", "22-Jul"}}) {
            var row = page.items().stream().filter(e -> e.sourceTestId().equals(expected[0])).findFirst().orElseThrow();
            assertNull(row.date());
            assertEquals(expected[1], row.dateRaw());
            var detail = experiments.detail(row.experimentId());
            assertNull(detail.date());
            assertEquals(expected[1], detail.dateRaw());
        }
        var mvc = MockMvcBuilders.standaloneSetup(new ExperimentController(experiments)).build();
        mvc.perform(get("/api/v1/experiments").param("investigationId", "PSI-101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[1].sourceTestId").value("51a"))
                .andExpect(jsonPath("$.items[1].date").isEmpty())
                .andExpect(jsonPath("$.items[1].dateRaw").value("22-Jul"));
        mvc.perform(get("/api/v1/experiments/PSI-101:run-0002"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.dateRaw").value("22-Jul"))
                .andExpect(jsonPath("$.date").isEmpty());
    }

    @Test
    void fullFlexDatesAndAbsentSaffireDatesAreUnchanged() {
        var flex = experiments.list("PSI-69", null, 0, 1).items().getFirst();
        assertEquals(LocalDate.of(2009, 3, 5), flex.date());
        assertEquals("3/5/2009", flex.dateRaw());
        assertEquals(flex.date(), experiments.detail(flex.experimentId()).date());
        var saffire = experiments.list("PSI-100", null, 0, 2);
        assertEquals(2, saffire.totalElements());
        for (var sample : saffire.items()) {
            assertNull(sample.date());
            assertNull(sample.dateRaw());
            assertTrue(experiments.detail(sample.experimentId()).measurements().isEmpty());
        }
    }
}
