package com.pyrosphere.backend.exception;

import com.pyrosphere.backend.dto.ApiModels.ErrorBody;
import com.pyrosphere.backend.dto.ApiModels.ErrorResponse;
import jakarta.validation.ConstraintViolationException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResponse> handleApi(ApiException exception) {
        return build(exception.getStatus(), exception.getCode(), exception.getMessage(),
                exception.getDetails());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception) {
        List<Map<String, Object>> details = new ArrayList<>();
        exception.getBindingResult().getFieldErrors().forEach(error -> {
            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put("field", error.getField());
            detail.put("issue", error.getDefaultMessage());
            details.add(detail);
        });
        return build(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR",
                "The request body could not be validated.", details);
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ErrorResponse> handleConstraintViolation(
            ConstraintViolationException exception) {
        List<Map<String, Object>> details = new ArrayList<>();
        exception.getConstraintViolations().forEach(violation -> {
            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put("field", violation.getPropertyPath().toString());
            detail.put("issue", violation.getMessage());
            details.add(detail);
        });
        return build(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR",
                "The request could not be validated.", details);
    }

    @ExceptionHandler({
            MissingServletRequestParameterException.class,
            MethodArgumentTypeMismatchException.class,
            HttpMessageNotReadableException.class,
            IllegalArgumentException.class
    })
    public ResponseEntity<ErrorResponse> handleBadRequest(Exception exception) {
        return build(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR",
                "The request parameters are invalid.", List.of(detail("issue", exception.getMessage())));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception exception) {
        log.error("Beklenmeyen hata", exception);
        return build(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "An unexpected server error occurred.", List.of());
    }

    private static Map<String, Object> detail(String key, Object value) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put(key, value);
        return detail;
    }

    private static ResponseEntity<ErrorResponse> build(HttpStatus status, String code,
                                                       String message,
                                                       List<Map<String, Object>> details) {
        ErrorResponse response = new ErrorResponse(
                UUID.randomUUID().toString(),
                new ErrorBody(code, message, details == null ? List.of() : details));
        return ResponseEntity.status(status).body(response);
    }
}
