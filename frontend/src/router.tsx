import { createBrowserRouter, Navigate } from "react-router";

import { RequireAuth } from "./auth/RequireAuth";
import Dashboard from "./pages/app/Dashboard";
import Forecast from "./pages/app/Forecast";
import Planning from "./pages/app/Planning";
import Products from "./pages/app/Products";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import { LazyStyleguide } from "./pages/styleguide/LazyStyleguide";

export const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/login", element: <Login /> },
  // Linked from nowhere: a review tool for the design tokens.
  { path: "/styleguide", element: <LazyStyleguide /> },
  {
    path: "/app",
    element: <RequireAuth />,
    children: [
      { index: true, element: <Navigate to="dashboard" replace /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "products", element: <Products /> },
      { path: "forecast", element: <Forecast /> },
      { path: "planning", element: <Planning /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
