package com.btfviewer.eclipse.bridge;

import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.btfviewer.eclipse.util.JsonUtil;

public record BTFBrowserMessage(String type, String json) {
    private static final Pattern TYPE = Pattern.compile(
            "\\\"type\\\"\\s*:\\s*\\\"((?:\\\\.|[^\\\"\\\\])*)\\\"");
    private static final Set<String> ALLOWED_TYPES = Set.of(
            "viewerReady", "traceLoaded", "traceLoadFailed", "timestampSelected",
            "evidenceSelected", "compareRequested", "exportRequested", "statusChanged");

    public static BTFBrowserMessage parse(String json) {
        if (json == null || json.length() > 256_000) {
            throw new IllegalArgumentException("Bridge message is empty or too large");
        }
        String trimmed = json.trim();
        if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
            throw new IllegalArgumentException("Bridge message must be a JSON object");
        }
        Matcher matcher = TYPE.matcher(trimmed);
        if (!matcher.find()) throw new IllegalArgumentException("Bridge message has no type");
        String type = JsonUtil.unescapeJsonString(matcher.group(1));
        if (!ALLOWED_TYPES.contains(type)) {
            throw new IllegalArgumentException("Unsupported bridge message type: " + type);
        }
        return new BTFBrowserMessage(type, trimmed);
    }

    public String stringValue(String key) {
        if (key == null || key.isEmpty()) return null;
        Pattern valuePattern = Pattern.compile(
                "\\\"" + Pattern.quote(key) + "\\\"\\s*:\\s*\\\"((?:\\\\.|[^\\\"\\\\])*)\\\"");
        Matcher matcher = valuePattern.matcher(json);
        return matcher.find() ? JsonUtil.unescapeJsonString(matcher.group(1)) : null;
    }
}
