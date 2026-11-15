package com.pyrosphere.backend.controller;

import com.pyrosphere.backend.dto.ApiModels.SourceView;
import com.pyrosphere.backend.service.CatalogService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class SourceController {

    private final CatalogService catalogService;

    public SourceController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/sources/{sourceId}")
    public SourceView source(@PathVariable String sourceId) {
        return catalogService.findSource(sourceId);
    }
}
