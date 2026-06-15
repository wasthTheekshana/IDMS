export default function Home() {
  return (
    <main
      style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: "800px" }}
    >
      <h1>IDMS</h1>
      <p>Intelligent Document Management System</p>
      <ul>
        <li>
          <a href="http://localhost:8000/api/docs">API Docs (Swagger)</a>
        </li>
        <li>
          <a href="http://localhost:8000/healthz">API Liveness</a>
        </li>
        <li>
          <a href="http://localhost:8000/readyz">API Readiness</a>
        </li>
      </ul>
    </main>
  );
}
