import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../services/auth";

export default function AuthCallback() {
  const { completeSignIn } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    completeSignIn()
      .then(() => active && navigate("/", { replace: true }))
      .catch(() => active && setError("Sign-in could not be completed. Please try again."));
    return () => {
      active = false;
    };
  }, [completeSignIn, navigate]);

  return (
    <div className="mx-auto max-w-xl px-5 py-24 text-center text-sm text-ink-dim">
      {error || "Completing secure sign-in…"}
    </div>
  );
}
