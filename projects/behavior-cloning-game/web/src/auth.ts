import { Amplify } from 'aws-amplify';
import { fetchAuthSession, fetchUserAttributes, getCurrentUser, signInWithRedirect, signOut } from 'aws-amplify/auth';
import { cognitoUserPoolsTokenProvider } from 'aws-amplify/auth/cognito';
import { CookieStorage } from 'aws-amplify/utils';

export type AuthConfig = {
  authentication_enabled: boolean;
  service_enabled: boolean;
  user_pool_id: string | null;
  client_id: string | null;
  domain: string | null;
};

let activeConfig: AuthConfig | null = null;

export async function loadAuthConfig(): Promise<AuthConfig> {
  const response = await fetch('/api/v1/auth/config', { cache: 'no-store' });
  if (!response.ok) throw new Error('Could not load the service configuration.');
  const config: AuthConfig = await response.json();
  activeConfig = config;
  if (config.authentication_enabled) {
    if (!config.user_pool_id || !config.client_id || !config.domain) {
      throw new Error('The sign-in service is not configured correctly.');
    }
    Amplify.configure({
      Auth: {
        Cognito: {
          userPoolId: config.user_pool_id,
          userPoolClientId: config.client_id,
          loginWith: {
            oauth: {
              domain: config.domain,
              scopes: ['openid', 'email'],
              redirectSignIn: [`${window.location.origin}/`],
              redirectSignOut: [`${window.location.origin}/`],
              responseType: 'code',
            },
          },
        },
      },
    });
    cognitoUserPoolsTokenProvider.setKeyValueStorage(new CookieStorage({
      domain: window.location.hostname,
      path: '/',
      sameSite: 'lax',
      secure: window.location.protocol === 'https:',
      expires: 7,
    }));
  }
  return config;
}

export async function currentSession(): Promise<{ signedIn: boolean; username: string | null }> {
  const session = await fetchAuthSession();
  if (!session.tokens?.accessToken) return { signedIn: false, username: null };
  try {
    const user = await getCurrentUser();
    let username = user.username;
    try {
      const attributes = await fetchUserAttributes();
      username = attributes.name?.trim() || username;
    } catch {
      // Keep the Cognito username as a fallback if the name attribute is unavailable.
    }
    return { signedIn: true, username };
  } catch {
    return { signedIn: true, username: null };
  }
}

export async function accessToken(): Promise<string | null> {
  const session = await fetchAuthSession();
  return session.tokens?.accessToken?.toString() ?? null;
}

export async function beginSignIn(): Promise<void> {
  await signInWithRedirect();
}

export async function endSignIn(): Promise<void> {
  await signOut({ global: true });
  if (activeConfig?.domain && activeConfig.client_id) {
    const logout = new URL(`https://${activeConfig.domain}/logout`);
    logout.searchParams.set('client_id', activeConfig.client_id);
    logout.searchParams.set('logout_uri', `${window.location.origin}/`);
    window.location.assign(logout);
  }
}
