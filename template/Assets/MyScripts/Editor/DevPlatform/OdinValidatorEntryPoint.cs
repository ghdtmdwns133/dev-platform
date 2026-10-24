using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace ProjectDelta.Editor.DevPlatform
{
    /// <summary>
    /// Batchmode entry point for the optional Odin Validator bridge:
    ///   Unity.exe -batchmode -projectPath &lt;root&gt;
    ///     -executeMethod ProjectDelta.Editor.DevPlatform.OdinValidatorEntryPoint.Run
    ///     -odinReportPath artifacts/reports/unity/odin.json
    ///
    /// The method always writes a JSON report and exits: 0 when the validator passed or is not
    /// installed, 1 when it reported errors, 3 when the run itself failed. No '-quit' is passed;
    /// the entry point owns process termination.
    /// </summary>
    public static class OdinValidatorEntryPoint
    {
        public const string DefaultReportRelativePath = "artifacts/reports/unity/odin.json";

        const string ReportArgument = "-odinReportPath";

        public static void Run()
        {
            string reportPath = null;
            int exitCode = 3;
            try
            {
                reportPath = ResolveReportPath(Environment.GetCommandLineArgs());
                OdinValidationReport report = OdinValidatorAdapter.Validate();
                OdinValidationReportWriter.Write(reportPath, report);
                Debug.Log("[OdinValidator] status=" + report.status
                    + " results=" + report.resultCount
                    + " errors=" + report.errorCount
                    + " warnings=" + report.warningCount);
                exitCode = report.ExitCode;
            }
            catch (Exception exception)
            {
                Debug.LogError("[OdinValidator] " + exception);
                exitCode = 3;
                TryWriteErrorReport(reportPath, exception);
            }

            EditorApplication.Exit(exitCode);
        }

        /// <summary>Resolves '-odinReportPath &lt;path&gt;' relative to the Unity project root.</summary>
        public static string ResolveReportPath(string[] commandLineArgs)
        {
            if (commandLineArgs != null)
            {
                for (int i = 0; i < commandLineArgs.Length; i++)
                {
                    string argument = commandLineArgs[i];
                    if (string.IsNullOrEmpty(argument))
                        continue;

                    if (argument.StartsWith(ReportArgument + "=", StringComparison.OrdinalIgnoreCase))
                    {
                        string inlineValue = argument.Substring(ReportArgument.Length + 1);
                        if (!string.IsNullOrEmpty(inlineValue))
                            return MakeAbsolute(inlineValue);
                    }

                    if (!string.Equals(argument.TrimStart('-'), ReportArgument.TrimStart('-'),
                            StringComparison.OrdinalIgnoreCase))
                        continue;

                    if (i + 1 < commandLineArgs.Length && !string.IsNullOrEmpty(commandLineArgs[i + 1]))
                        return MakeAbsolute(commandLineArgs[i + 1]);
                }
            }

            return MakeAbsolute(DefaultReportRelativePath);
        }

        static string MakeAbsolute(string path)
        {
            if (Path.IsPathRooted(path))
                return Path.GetFullPath(path);

            string projectRoot = Path.GetDirectoryName(Application.dataPath);
            if (string.IsNullOrEmpty(projectRoot))
                projectRoot = Environment.CurrentDirectory;
            return Path.GetFullPath(Path.Combine(projectRoot, path));
        }

        static void TryWriteErrorReport(string reportPath, Exception exception)
        {
            try
            {
                string path = string.IsNullOrEmpty(reportPath)
                    ? ResolveReportPath(Array.Empty<string>())
                    : reportPath;
                OdinValidationReport report = OdinValidationReport.Error(
                    "Odin validation failed: " + exception.Message,
                    null);
                OdinValidationReportWriter.Write(path, report);
            }
            catch (Exception writeException)
            {
                Debug.LogError("[OdinValidator] could not write failure report: " + writeException.Message);
            }
        }
    }
}
