import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
  type User,
} from "oidc-client-ts";
import { registerAccessTokenReader } from "./authToken";

interface AuthContextValue {
  user: User | null;
  ready: boolean;
  configured: boolean;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
  completeSignIn(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const region = import.meta.env.VITE_COGNITO_REGION || "us-east-1";
const poolId = import.meta.env.VITE_COGNITO_USER_POOL_ID || "";
const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID || "";
const configured = Boolean(poolId && clientId);

// Keep bearer and refresh tokens in memory. Only temporary OAuth state/PKCE
// material uses sessionStorage so the authorization redirect can round-trip.
const manager = configured
  ? new UserManager({
      authority: `https://cognito-idp.${region}.amazonaws.com/${poolId}`,
      client_id: clientId,
      redirect_uri: `${window.location.origin}/auth/callback`,
      post_logout_redirect_uri: window.location.origin,
      response_type: "code",
      scope: "openid email profile",
      automaticSilentRenew: true,
      monitorSession: false,
      loadUserInfo: false,
      userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
      stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    })
  : null;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const unregisterTokenReader = registerAccessTokenReader(async () => {
      if (!manager) return null;
      const current = await manager.getUser();
      if (!current) return null;
      if (current.expired) {
        try {
          const refreshed = await manager.signinSilent();
          return refreshed?.access_token || null;
        } catch {
          await manager.removeUser();
          return null;
        }
      }
      return current.access_token;
    });
    if (!manager) {
      setReady(true);
      return unregisterTokenReader;
    }
    let active = true;
    const loaded = (next: User) => {
      if (active) setUser(next);
    };
    const unloaded = () => {
      if (active) setUser(null);
    };
    manager.events.addUserLoaded(loaded);
    manager.events.addUserUnloaded(unloaded);
    manager
      .getUser()
      .then((current) => {
        if (active) setUser(current);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
      unregisterTokenReader();
      manager.events.removeUserLoaded(loaded);
      manager.events.removeUserUnloaded(unloaded);
    };
  }, []);

  const signIn = useCallback(async () => {
    if (!manager) throw new Error("Cognito sign-in is not configured");
    await manager.signinRedirect();
  }, []);

  const signOut = useCallback(async () => {
    if (!manager) return;
    await manager.signoutRedirect();
  }, []);

  const completeSignIn = useCallback(async () => {
    if (!manager) throw new Error("Cognito sign-in is not configured");
    const result = await manager.signinRedirectCallback();
    setUser(result);
  }, []);

  const value = useMemo(
    () => ({ user, ready, configured, signIn, signOut, completeSignIn }),
    [user, ready, signIn, signOut, completeSignIn],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
