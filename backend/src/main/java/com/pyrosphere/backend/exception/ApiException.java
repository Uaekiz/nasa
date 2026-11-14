package com.pyrosphere.backend.exception;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;

/** Domain exception rendered through the contract error envelope. */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;
    private final List<Map<String, Object>> details;

    public ApiException(HttpStatus status, String code, String message) {
        this(status, code, message, List.of());
    }

    public ApiException(HttpStatus status, String code, String message,
                        List<Map<String, Object>> details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = details == null ? List.of() : List.copyOf(details);
    }

    public static ApiException validation(String message, List<Map<String, Object>> details) {
        return new ApiException(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", message, details);
    }

    public static ApiException notFound(String code, String message) {
        return new ApiException(HttpStatus.NOT_FOUND, code, message);
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }

    public List<Map<String, Object>> getDetails() {
        return details;
    }
}
