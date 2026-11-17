using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;

internal static class McpLauncher
{
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
                Task input = Console.OpenStandardInput().CopyToAsync(child.StandardInput.BaseStream);
                input.ContinueWith(task =>
                {
                    if (task.IsFaulted)
                        Console.Error.WriteLine("2MD-MCP: no se pudo transmitir stdin.");
                    try { child.StandardInput.Close(); }
                    catch (InvalidOperationException) { }
                });
                Task output = child.StandardOutput.BaseStream.CopyToAsync(Console.OpenStandardOutput());
                Task errors = child.StandardError.BaseStream.CopyToAsync(Console.OpenStandardError());
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
