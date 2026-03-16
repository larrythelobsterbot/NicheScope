import { createClient, type Client } from "@libsql/client";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Params = any[] | Record<string, any>;

let client: Client | null = null;

function getClient(): Client {
  if (!client) {
    const url = process.env.TURSO_DATABASE_URL;
    const authToken = process.env.TURSO_AUTH_TOKEN;

    if (!url) {
      throw new Error(
        "TURSO_DATABASE_URL is not set. Create a Turso database and set the env var."
      );
    }

    client = createClient({
      url,
      authToken,
    });
  }
  return client;
}

export async function queryAll<T>(sql: string, params: Params = []): Promise<T[]> {
  const result = await getClient().execute({ sql, args: params });
  return result.rows as unknown as T[];
}

export async function queryOne<T>(sql: string, params: Params = []): Promise<T | undefined> {
  const result = await getClient().execute({ sql, args: params });
  return (result.rows[0] as unknown as T) ?? undefined;
}

export async function execute(sql: string, params: Params = []) {
  return getClient().execute({ sql, args: params });
}
