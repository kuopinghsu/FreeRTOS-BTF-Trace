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
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.eclipse.core.resources.IFile;
import org.eclipse.core.runtime.FileLocator;
import org.eclipse.core.runtime.Path;
import org.osgi.framework.Bundle;

/** Loopback-only server for the single-file viewer and streamed workspace trace. */
public final class ViewerResourceServer implements AutoCloseable {
    private final Bundle bundle;
    private final IFile trace;
    private final String token = UUID.randomUUID().toString();
    private final ServerSocket server;
    private final ExecutorService executor;
    private volatile boolean closed;

    public ViewerResourceServer(Bundle bundle, IFile trace) throws IOException {
        this.bundle = bundle;
        this.trace = trace;
        this.server = new ServerSocket(0, 16, InetAddress.getLoopbackAddress());
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
        String name = URLEncoder.encode(trace.getName(), StandardCharsets.UTF_8).replace("+", "%20");
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
                if (!closed) error.printStackTrace();
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
                try (InputStream content = trace.getContents()) {
                    sendStream(out, content, "application/octet-stream", head);
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
        writeHeaders(out, 200, "OK", contentType);
        if (!head) content.transferTo(out);
        out.flush();
    }

    private static void sendStatus(OutputStream out, int code, String reason) throws IOException {
        byte[] body = reason.getBytes(StandardCharsets.UTF_8);
        writeHeaders(out, code, reason, "text/plain; charset=utf-8");
        out.write(body);
        out.flush();
    }

    private static void writeHeaders(OutputStream out, int code, String reason, String type)
            throws IOException {
        String headers = "HTTP/1.1 " + code + " " + reason + "\r\n"
                + "Content-Type: " + type + "\r\n"
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

    @Override
    public void close() {
        closed = true;
        try { server.close(); } catch (IOException ignored) {}
        executor.shutdownNow();
    }
}

