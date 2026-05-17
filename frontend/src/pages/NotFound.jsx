import { Home } from "lucide-react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main className="not-found">
      <section>
        <span>404</span>
        <h1>Страница не найдена</h1>
        <Link to="/" className="primary-button">
          <Home size={18} /> Dashboard
        </Link>
      </section>
    </main>
  );
}
