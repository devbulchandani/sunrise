// Isolated token accessor avoids importing React hooks into the API module.
let tokenReader: (() => Promise<string | null>) | null = null;

export function registerAccessTokenReader(reader: () => Promise<string | null>) {
  tokenReader = reader;
  return () => {
    if (tokenReader === reader) tokenReader = null;
  };
}

export async function getCurrentAccessToken(): Promise<string | null> {
  return tokenReader ? tokenReader() : null;
}
