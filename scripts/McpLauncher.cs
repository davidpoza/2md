using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;

internal static class McpLauncher
{
    private static async Task ForwardAsync(Stream source, Stream destination)
    {
        var buffer = new byte[8192];
        int count;
        while ((count = await source.ReadAsync(buffer, 0, buffer.Length)) != 0)
        {
            await destination.WriteAsync(buffer, 0, count);
            // A protocol message must reach its reader before we wait for the next one.
            await destination.FlushAsync();
        }
    }

    private static int Main()
    {
        try
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            var start = new ProcessStartInfo
            {
                FileName = Path.Combine(root, "2MD.exe"),
                Arguments = "\"" + Path.Combine(root, "resources", "app", "app", "mcp-entry.js") + "\"",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = root
            };
            start.EnvironmentVariables["ELECTRON_RUN_AS_NODE"] = "1";
            using (var child = Process.Start(start))
            {
                Task input = Task.Run(() => ForwardAsync(Console.OpenStandardInput(), child.StandardInput.BaseStream));
                input.ContinueWith(task =>
                {
                    if (task.IsFaulted)
                        Console.Error.WriteLine("2MD-MCP: no se pudo transmitir stdin.");
                    try { child.StandardInput.Close(); }
                    catch (InvalidOperationException) { }
                });
                Task output = Task.Run(() => ForwardAsync(child.StandardOutput.BaseStream, Console.OpenStandardOutput()));
                Task errors = Task.Run(() => ForwardAsync(child.StandardError.BaseStream, Console.OpenStandardError()));
                child.WaitForExit();
                Task.WaitAll(output, errors);
                return child.ExitCode;
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("No se puede iniciar 2MD-MCP: " + error.Message);
            return 1;
        }
    }
}
