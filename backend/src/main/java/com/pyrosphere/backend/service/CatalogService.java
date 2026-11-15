package com.pyrosphere.backend.service;

import com.pyrosphere.backend.dto.ApiModels.InvestigationList;
import com.pyrosphere.backend.dto.ApiModels.InvestigationView;
import com.pyrosphere.backend.dto.ApiModels.SourceView;
import com.pyrosphere.backend.exception.ApiException;
import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final JdbcClient jdbc;

    public CatalogService(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public InvestigationList listInvestigations() {
        List<InvestigationView> items = jdbc.sql("""
                        SELECT investigation_id, name, description, available_data_types
                        FROM core.investigations
                        ORDER BY investigation_id
                        """)
                .query((rs, rowNum) -> new InvestigationView(
                        rs.getString("investigation_id"),
                        rs.getString("name"),
                        rs.getString("description"),
                        stringArray(rs, "available_data_types")))
                .list();
        return new InvestigationList(items);
    }

    public void requireInvestigation(String investigationId) {
        boolean exists = jdbc.sql(
                        "SELECT exists(SELECT 1 FROM core.investigations WHERE investigation_id = :id)")
                .param("id", investigationId)
                .query(Boolean.class)
                .single();
        if (!exists) {
            throw ApiException.notFound("INVESTIGATION_NOT_FOUND",
                    "The requested investigation was not found: " + investigationId);
        }
    }

    public SourceView findSource(String sourceId) {
        return jdbc.sql("""
                        SELECT source_id, title, source_type, investigation_id, doi,
                               original_url, document_url
                        FROM core.sources
                        WHERE source_id = :sourceId
                        """)
                .param("sourceId", sourceId)
                .query((rs, rowNum) -> mapSource(rs))
                .optional()
                .orElseThrow(() -> ApiException.notFound("SOURCE_NOT_FOUND",
                        "The requested source was not found: " + sourceId));
    }

    public List<SourceView> findSources(List<String> sourceIds) {
        if (sourceIds == null || sourceIds.isEmpty()) {
            return List.of();
        }
        Map<String, SourceView> byId = new LinkedHashMap<>();
        for (String sourceId : sourceIds) {
            if (!byId.containsKey(sourceId)) {
                byId.put(sourceId, findSource(sourceId));
            }
        }
        return new ArrayList<>(byId.values());
    }

    public static SourceView mapSource(ResultSet rs) throws SQLException {
        return new SourceView(
                rs.getString("source_id"),
                rs.getString("title"),
                rs.getString("source_type"),
                rs.getString("investigation_id"),
                rs.getString("doi"),
                rs.getString("original_url"),
                rs.getString("document_url"));
    }

    private static List<String> stringArray(ResultSet rs, String column) throws SQLException {
        Array array = rs.getArray(column);
        if (array == null) {
            return List.of();
        }
        Object value = array.getArray();
        if (value instanceof String[] strings) {
            return List.of(strings);
        }
        if (value instanceof Object[] objects) {
            List<String> result = new ArrayList<>();
            for (Object object : objects) {
                result.add(String.valueOf(object));
            }
            return result;
        }
        return List.of();
    }
}
