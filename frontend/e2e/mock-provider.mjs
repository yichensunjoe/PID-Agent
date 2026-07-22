import http from "node:http";

const server = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);

  response.setHeader("Content-Type", "application/json");
  if (request.url === "/health") {
    response.end(JSON.stringify({ status: "ok" }));
    return;
  }
  if (request.method === "GET" && request.url === "/v1/models") {
    response.end(JSON.stringify({ data: [{ id: "test-model", owned_by: "e2e" }] }));
    return;
  }
  if (request.method === "POST" && request.url === "/v1/chat/completions") {
    response.end(JSON.stringify({ choices: [{ message: { content: "OK" } }] }));
    return;
  }
  response.statusCode = 404;
  response.end(JSON.stringify({ error: "not_found" }));
});

server.listen(8999, "127.0.0.1");
