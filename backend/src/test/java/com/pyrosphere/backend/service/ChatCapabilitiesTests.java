package com.pyrosphere.backend.service;

import com.pyrosphere.backend.controller.ComparisonChatController;
import com.pyrosphere.backend.exception.ApiException;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ChatCapabilitiesTests {
    @Test
    void proxyReturnsOnlyTheRagResponseThroughTheController() throws Exception {
        var builder = RestClient.builder().baseUrl("http://rag.test");
        var server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo("http://rag.test/rag/v1/capabilities")).andRespond(withSuccess(
                "{\"status\":\"READY\",\"language\":\"en\",\"items\":[{\"investigationId\":\"PSI-25\",\"sourceIds\":[\"actual-test-source\"],\"examples\":[\"Show BASS-II test B1.\"]}]}", MediaType.APPLICATION_JSON));
        var service = new ChatService(builder.build(), null);
        var mvc = MockMvcBuilders.standaloneSetup(new ComparisonChatController(null, service)).build();
        mvc.perform(get("/api/v1/chat/capabilities")).andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].investigationId").value("PSI-25"))
                .andExpect(jsonPath("$.language").value("en"));
        server.verify();
    }

    @Test
    void failedScopeInspectionRaisesAnApiErrorWithoutFallbackCatalog() {
        var builder = RestClient.builder().baseUrl("http://rag.test");
        var server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo("http://rag.test/rag/v1/capabilities")).andRespond(withServerError());
        var service = new ChatService(builder.build(), null);
        assertThrows(ApiException.class, service::capabilities);
        server.verify();
    }
}
