package com.btfviewer.eclipse.resources;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.eclipse.core.resources.IFile;
import org.eclipse.core.runtime.FileLocator;
import org.eclipse.core.runtime.Path;
import org.osgi.framework.Bundle;

import com.btfviewer.eclipse.BTFViewerPlugin;

/** Loopback-only server for the single-file viewer and streamed trace. */
public final class ViewerResourceServer implements AutoCloseable {
    private static final long MAX_TRACE_BYTES = 256L * 1024 * 1024;

    private final Bundle bundle;
    private final TraceSource trace;
    private final String token = UUID.randomUUID().toString();
    private final ServerSocket server;
    private final ExecutorService executor;
    private volatile boolean closed;

    public ViewerResourceServer(Bundle bundle, IFile trace) throws IOException {
        this(bundle, workspaceTrace(trace));
    }

    public ViewerResourceServer(Bundle bundle, java.nio.file.Path trace) throws IOException {
        this(bundle, localTrace(trace));
    }

    private ViewerResourceServer(Bundle bundle, TraceSource trace) throws IOException {
        this.bundle = bundle;
        this.trace = trace;
        this.server = new ServerSocket(0, 16, InetAddress.getByAddress(new byte[] { 127, 0, 0, 1 }));
        this.executor = Executors.newCachedThreadPool(runnable -> {
            Thread thread = new Thread(runnable, "BTFViewer-resource-server");
            thread.setDaemon(true);
            return thread;
        });
        executor.execute(this::acceptLoop);
    }

    public URI viewerUri() {
        return uri("/viewer/" + token + "/index.html");
    }

    public URI traceUri() {
        String name = URLEncoder.encode(trace.name(), StandardCharsets.UTF_8).replace("+", "%20");
        return uri("/trace/" + token + "/" + name);
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + server.getLocalPort() + path);
    }

    private void acceptLoop() {
        while (!closed) {
            try {
                Socket socket = server.accept();
                executor.execute(() -> serve(socket));
            } catch (IOException error) {
                if (!closed) BTFViewerPlugin.log("The embedded viewer resource server stopped unexpectedly.", error);
            }
        }
    }

    private void serve(Socket socket) {
        try (socket;
             InputStream rawIn = new BufferedInputStream(socket.getInputStream());
             OutputStream out = new BufferedOutputStream(socket.getOutputStream())) {
            String requestLine = readLine(rawIn);
            String line;
            do { line = readLine(rawIn); } while (line != null && !line.isEmpty());
            if (requestLine == null) return;
            String[] parts = requestLine.split(" ", 3);
            if (parts.length < 2 || !(parts[0].equals("GET") || parts[0].equals("HEAD"))) {
                sendStatus(out, 405, "Method Not Allowed");
                return;
            }
            boolean head = parts[0].equals("HEAD");
            String path = URI.create(parts[1]).getPath();
            if (path.equals("/viewer/" + token + "/index.html")) {
                var entry = bundle.getEntry("web/btf_viewer.html");
                if (entry == null) {
                    sendStatus(out, 500, "Viewer asset missing");
                    return;
                }
                try (InputStream content = FileLocator.openStream(bundle, new Path("web/btf_viewer.html"), false)) {
                    sendStream(out, content, "text/html; charset=utf-8", head);
                }
            } else if (path.startsWith("/trace/" + token + "/")) {
                if (trace.size() > MAX_TRACE_BYTES) {
                    sendStatus(out, 413, "Trace exceeds the 256 MB limit");
                    return;
                }
                try (InputStream content = trace.opener().open()) {
                    sendStream(out, content, "application/octet-stream", head,
                            trace.size(), MAX_TRACE_BYTES);
                }
            } else {
                sendStatus(out, 404, "Not Found");
            }
        } catch (Exception ignored) {
            // Browser cancellation and editor disposal commonly close the socket mid-response.
        }
    }

    private static void sendStream(OutputStream out, InputStream content, String contentType,
            boolean head) throws IOException {
        sendStream(out, content, contentType, head, -1, Long.MAX_VALUE);
    }

    private static void sendStream(OutputStream out, InputStream content, String contentType,
            boolean head, long contentLength, long maxBytes) throws IOException {
        writeHeaders(out, 200, "OK", contentType, contentLength);
        if (!head) {
            byte[] buffer = new byte[64 * 1024];
            long total = 0;
            int count;
            while ((count = content.read(buffer)) >= 0) {
                total += count;
                if (total > maxBytes) {
                    throw new IOException("Trace exceeded the configured byte limit while streaming");
                }
                out.write(buffer, 0, count);
            }
        }
        out.flush();
    }

    private static void sendStatus(OutputStream out, int code, String reason) throws IOException {
        byte[] body = reason.getBytes(StandardCharsets.UTF_8);
        writeHeaders(out, code, reason, "text/plain; charset=utf-8", body.length);
        out.write(body);
        out.flush();
    }

    private static void writeHeaders(OutputStream out, int code, String reason, String type,
            long contentLength)
            throws IOException {
        String headers = "HTTP/1.1 " + code + " " + reason + "\r\n"
                + "Content-Type: " + type + "\r\n"
                + (contentLength >= 0 ? "Content-Length: " + contentLength + "\r\n" : "")
                + "Cache-Control: no-store\r\n"
                + "X-Content-Type-Options: nosniff\r\n"
                + "Connection: close\r\n\r\n";
        out.write(headers.getBytes(StandardCharsets.US_ASCII));
    }

    private static String readLine(InputStream in) throws IOException {
        StringBuilder value = new StringBuilder();
        int ch;
        while ((ch = in.read()) >= 0) {
            if (ch == '\n') break;
            if (ch != '\r') value.append((char) ch);
            if (value.length() > 8192) throw new IOException("HTTP line too long");
        }
        return ch < 0 && value.isEmpty() ? null : value.toString();
    }

    private static TraceSource workspaceTrace(IFile trace) {
        java.io.File local = trace.getLocation() == null ? null : trace.getLocation().toFile();
        long size = local != null && local.isFile() ? local.length() : -1;
        return new TraceSource(trace.getName(), size, trace::getContents);
    }

    private static TraceSource localTrace(java.nio.file.Path trace) throws IOException {
        java.nio.file.Path local = trace.toAbsolutePath().normalize();
        if (!Files.isRegularFile(local) || !Files.isReadable(local)) {
            throw new IOException("Trace is not a readable local file: " + local);
        }
        java.nio.file.Path fileName = local.getFileName();
        String name = fileName == null ? local.toString() : fileName.toString();
        return new TraceSource(name, Files.size(local), () -> Files.newInputStream(local));
    }

    @FunctionalInterface
    private interface TraceOpener {
        InputStream open() throws Exception;
    }

    private record TraceSource(String name, long size, TraceOpener opener) {}

    @Override
    public void close() {
        closed = true;
        try { server.close(); } catch (IOException ignored) {}
        executor.shutdownNow();
    }
}
