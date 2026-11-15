package com.pyrosphere.backend.controller;

import com.pyrosphere.backend.exception.GlobalExceptionHandler;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.match.MockRestRequestMatchers;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ScenarioAnalysisControllerTests {
    private static final String PARAMS = """
            {"oxygenPercent":21,"pressureKpa":101.3,"airflowCmS":16,"gravityG":0.16,
             "temperatureC":23,"ignitionPowerW":85,"material":"PMMA Film",
             "flowDirection":"CONCURRENT","coPpm":18,"co2Percent":0.38}
            """;

    private static MockMvc mvc(RestClient client) {
        return MockMvcBuilders.standaloneSetup(new ScenarioAnalysisController(client))
                .setControllerAdvice(new GlobalExceptionHandler()).build();
    }

    private static String body(String params) {
        return "{\"capturedAt\":\"2026-11-15T12:00:00Z\",\"params\":" + params + "}";
    }

    @Test
    void forwardsAllInputsWithUnspecifiedGasPhasesAndKeepsDeterministicFallback() throws Exception {
        var builder = RestClient.builder().baseUrl("http://rag.test");
        var server = MockRestServiceServer.bindTo(builder).build();
        String forwarded = PARAMS.trim().replace("}", ",\"coMeasurementPhase\":\"UNSPECIFIED\",\"co2MeasurementPhase\":\"UNSPECIFIED\"}");
        server.expect(requestTo("http://rag.test/rag/v1/scenarios/evidence"))
                .andExpect(MockRestRequestMatchers.content().json("{\"material\":\"PMMA Film\",\"params\":" + forwarded + "}"))
                .andRespond(withSuccess("""
                        {"status":"EVIDENCE_FOUND","sources":[{"citationId":"S1","sourceId":"actual-source"}],
                         "narrative":{"status":"DETERMINISTIC","modelUsed":null,
                         "fallbackReason":"The ordering model is unavailable.","observations":[{"text":"Source comparison.","citationIds":["S1"]}]}}
                        """, MediaType.APPLICATION_JSON));
        mvc(builder.build()).perform(post("/api/v1/scenario-analyses").contentType(MediaType.APPLICATION_JSON).content(body(PARAMS)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("EVIDENCE_RETRIEVED"))
                .andExpect(jsonPath("$.params.pressureKpa").value(101.3))
                .andExpect(jsonPath("$.params.gravityG").value(0.16))
                .andExpect(jsonPath("$.params.temperatureC").value(23))
                .andExpect(jsonPath("$.params.ignitionPowerW").value(85))
                .andExpect(jsonPath("$.params.coMeasurementPhase").value("UNSPECIFIED"))
                .andExpect(jsonPath("$.evidence.narrative.status").value("DETERMINISTIC"))
                .andExpect(jsonPath("$.evidence.narrative.modelUsed").isEmpty())
                .andExpect(jsonPath("$.evidence.sources[0].citationId").value("S1"));
        server.verify();
    }

    @Test
    void acceptsExplicitGasPhasesWithoutForwardingTheLocalScreenshot() throws Exception {
        var builder = RestClient.builder().baseUrl("http://rag.test");
        var server = MockRestServiceServer.bindTo(builder).build();
        String params = PARAMS.trim().replace("}", ",\"coMeasurementPhase\":\"FINAL\",\"co2MeasurementPhase\":\"INITIAL\"}");
        server.expect(requestTo("http://rag.test/rag/v1/scenarios/evidence"))
                .andExpect(MockRestRequestMatchers.content().json("{\"material\":\"PMMA Film\",\"params\":" + params + "}"))
                .andRespond(withSuccess("{\"status\":\"INSUFFICIENT_EVIDENCE\",\"sources\":[]}", MediaType.APPLICATION_JSON));
        String request = body(params).replaceFirst("\\}$", ",\"imageDataUrl\":\"data:image/png;base64,local-only\"}");
        mvc(builder.build()).perform(post("/api/v1/scenario-analyses").contentType(MediaType.APPLICATION_JSON).content(request))
                .andExpect(status().isOk()).andExpect(jsonPath("$.params.coMeasurementPhase").value("FINAL"))
                .andExpect(jsonPath("$.params.co2MeasurementPhase").value("INITIAL"));
        server.verify();
    }

    @Test
    void rejectsInvalidOrIncompleteInputsBeforeCallingRag() throws Exception {
        var builder = RestClient.builder().baseUrl("http://rag.test");
        var server = MockRestServiceServer.bindTo(builder).build();
        MockMvc mvc = mvc(builder.build());
        for (String params : new String[] {
                PARAMS.replace("\"pressureKpa\":101.3", "\"pressureKpa\":0"),
                PARAMS.replace("\"gravityG\":0.16", "\"gravityG\":-1"),
                PARAMS.replace("\"temperatureC\":23", "\"temperatureC\":-274"),
                PARAMS.replace("\"ignitionPowerW\":85", "\"ignitionPowerW\":-1"),
                PARAMS.replace("\"co2Percent\":0.38", "\"co2Percent\":101"),
                PARAMS.replace("\"oxygenPercent\":21,", ""),
                PARAMS.replace("\"material\":\"PMMA Film\"", "\"material\":\" \""),
                PARAMS.replace("\"pressureKpa\":101.3", "\"pressureKpa\":NaN"),
                PARAMS.trim().replace("}", ",\"unexpected\":3}"),
                PARAMS.trim().replace("}", ",\"coMeasurementPhase\":\"GUESS\"}")}) {
            mvc.perform(post("/api/v1/scenario-analyses").contentType(MediaType.APPLICATION_JSON).content(body(params)))
                    .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
        }
        server.verify();
    }

    @Test
    void ragTimeoutUnavailableAndMalformedResponsesAreExplicitErrors() throws Exception {
        for (int upstream : new int[] {504, 503, 400, 200}) {
            var builder = RestClient.builder().baseUrl("http://rag.test");
            var server = MockRestServiceServer.bindTo(builder).build();
            server.expect(requestTo("http://rag.test/rag/v1/scenarios/evidence"))
                    .andRespond(withRawStatus(upstream).contentType(MediaType.APPLICATION_JSON).body("{}"));
            int expected = upstream == 504 ? 504 : upstream == 400 ? 400 : 503;
            String code = upstream == 504 ? "RAG_TIMEOUT" : upstream == 400 ? "VALIDATION_ERROR" : "RAG_UNAVAILABLE";
            mvc(builder.build()).perform(post("/api/v1/scenario-analyses").contentType(MediaType.APPLICATION_JSON).content(body(PARAMS)))
                    .andExpect(status().is(expected)).andExpect(jsonPath("$.error.code").value(code));
            server.verify();
        }
    }
}
