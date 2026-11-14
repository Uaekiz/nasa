package com.pyrosphere.backend.controller;

import com.pyrosphere.backend.dto.ApiModels.InvestigationList;
import com.pyrosphere.backend.service.CatalogService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class InvestigationController {

    private final CatalogService catalogService;

    public InvestigationController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/investigations")
    public InvestigationList investigations() {
        return catalogService.listInvestigations();
    }
}
