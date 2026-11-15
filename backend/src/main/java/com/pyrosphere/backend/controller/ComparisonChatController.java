package com.pyrosphere.backend.controller;

import com.pyrosphere.backend.dto.ApiModels.ChatRequest;
import com.pyrosphere.backend.dto.ApiModels.ComparisonRequest;
import com.pyrosphere.backend.dto.ApiModels.ComparisonResponse;
import com.pyrosphere.backend.service.ChatService;
import com.pyrosphere.backend.service.ComparisonService;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class ComparisonChatController {

    private final ComparisonService comparisonService;
    private final ChatService chatService;

    public ComparisonChatController(ComparisonService comparisonService,
                                    ChatService chatService) {
        this.comparisonService = comparisonService;
        this.chatService = chatService;
    }

    @PostMapping("/comparisons")
    public ComparisonResponse comparisons(@RequestBody(required = false) ComparisonRequest request) {
        return comparisonService.compare(request == null ? null : request.experimentIds());
    }

    @PostMapping("/chat")
    public Map<String, Object> chat(@RequestBody ChatRequest request) {
        return chatService.chat(request);
    }

    @GetMapping("/chat/capabilities")
    public Map<String, Object> capabilities() {
        return chatService.capabilities();
    }
}
