using System;
using System.Diagnostics;
using System.Linq;

internal static class SparkSubmitShim
{
    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static int Main(string[] args)
    {
        var script = System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "spark-submit.cmd");
        System.IO.File.WriteAllLines(System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "spark-submit-shim.args.log"), args);
        var arguments = "/d /c \"\"" + script + "\" " + string.Join(" ", args.Select(Quote)) + "\"";
        using (var process = Process.Start(new ProcessStartInfo("cmd.exe", arguments) { UseShellExecute = false }))
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }
}
