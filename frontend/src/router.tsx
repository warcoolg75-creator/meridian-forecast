import { createBrowserRouter, Navigate, type UIMatch } from "react-router";

import { RedirectIfSignedIn } from "./auth/RedirectIfSignedIn";
import { RequireAuth } from "./auth/RequireAuth";
import { PLANNING_ROLES } from "./auth/roles";
import { AppLayout } from "./components/shell/AppLayout";
import Dashboard from "./pages/app/Dashboard";
import Evidence from "./pages/app/forecast/Evidence";
import ForecastOverview from "./pages/app/forecast/ForecastOverview";
import SkuForecastPage from "./pages/app/forecast/SkuForecastPage";
import Planning from "./pages/app/Planning";
import { ProductCrumb } from "./pages/app/ProductCrumb";
import ProductDetail from "./pages/app/ProductDetail";
import Products from "./pages/app/Products";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import { LazyComponents, LazyStyleguide } from "./pages/styleguide/LazyStyleguide";

export const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  {
    path: "/login",
    element: (
      <RedirectIfSignedIn>
        <Login />
      </RedirectIfSignedIn>
    ),
  },
  // Linked from nowhere: review tools for the design tokens and the component library.
  { path: "/styleguide", element: <LazyStyleguide /> },
  { path: "/styleguide/components", element: <LazyComponents /> },
  {
    path: "/app",
    element: <RequireAuth />,
    children: [
      {
        // A route's `handle.crumb` puts it in the top bar's breadcrumb.
        element: <AppLayout />,
        handle: { crumb: "Meridian" },
        children: [
          { index: true, element: <Navigate to="dashboard" replace /> },
          { path: "dashboard", element: <Dashboard />, handle: { crumb: "Dashboard" } },
          {
            path: "products",
            handle: { crumb: "Products" },
            children: [
              { index: true, element: <Products /> },
              {
                path: ":sku",
                element: <ProductDetail />,
                handle: {
                  crumb: (match: UIMatch) => <ProductCrumb sku={match.params.sku ?? ""} />,
                },
              },
            ],
          },
          {
            path: "forecast",
            handle: { crumb: "Forecast" },
            children: [
              { index: true, element: <ForecastOverview /> },
              // A fixed segment outranks :sku in React Router, so "evidence" is never a SKU.
              { path: "evidence", element: <Evidence />, handle: { crumb: "Model evidence" } },
              {
                path: ":sku",
                element: <SkuForecastPage />,
                handle: {
                  crumb: (match: UIMatch) => <ProductCrumb sku={match.params.sku ?? ""} />,
                },
              },
            ],
          },
          {
            // Production planning changes the plan: admins and planners only, as on the API.
            element: <RequireAuth roles={PLANNING_ROLES} />,
            children: [{ path: "planning", element: <Planning />, handle: { crumb: "Planning" } }],
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
