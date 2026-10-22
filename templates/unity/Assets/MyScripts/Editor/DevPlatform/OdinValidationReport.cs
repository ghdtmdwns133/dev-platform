using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

namespace ProjectDelta.Editor.DevPlatform
{
    /// <summary>
    /// Serialized outcome of one Odin Validator probe, written for devctl to read.
    /// Public field names are the JSON contract; changing them requires a matching devctl change.
    /// </summary>
    [Serializable]
    public sealed class OdinValidationReport
    {
        public const string StatusSkipped = "skipped";
        public const string StatusPassed = "passed";
        public const string StatusFailed = "failed";
        public const string StatusError = "error";

        public string status;
        public string reason;
        public string hint;
        public string unityVersion;
        public string generatedAtUtc;
        public int resultCount;
        public int errorCount;
        public int warningCount;
        public List<string> probed = new List<string>();
        public List<string> errors = new List<string>();
        public List<string> warnings = new List<string>();

        public OdinValidationReport()
        {
            unityVersion = Application.unityVersion;
            generatedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
        }

        /// <summary>Exit code for the batchmode process: 0 pass/skip, 1 validation errors, 3 execution failure.</summary>
        public int ExitCode
        {
            get
            {
                switch (status)
                {
                    case StatusPassed:
                    case StatusSkipped:
                        return 0;
                    case StatusFailed:
                        return 1;
                    default:
                        return 3;
                }
            }
        }

        public static OdinValidationReport Skipped(string reason, List<string> probed, string hint)
        {
            OdinValidationReport report = new OdinValidationReport();
            report.status = StatusSkipped;
            report.reason = reason;
            report.hint = hint;
            report.probed = probed ?? new List<string>();
            return report;
        }

        public static OdinValidationReport Completed(
            int resultCount,
            int errorCount,
            int warningCount,
            List<string> errors,
            List<string> warnings,
            List<string> probed)
        {
            OdinValidationReport report = new OdinValidationReport();
            report.status = errorCount > 0 ? StatusFailed : StatusPassed;
            report.resultCount = resultCount;
            report.errorCount = errorCount;
            report.warningCount = warningCount;
            report.errors = errors ?? new List<string>();
            report.warnings = warnings ?? new List<string>();
            report.probed = probed ?? new List<string>();
            if (errorCount > 0)
                report.reason = "Odin Validator reported errors";
            else if (resultCount == 0)
                report.reason = "Odin Validator reported no findings";
            else
                report.reason = "Odin Validator reported no errors";
            return report;
        }

        public static OdinValidationReport Error(string reason, List<string> probed)
        {
            OdinValidationReport report = new OdinValidationReport();
            report.status = StatusError;
            report.reason = reason;
            report.probed = probed ?? new List<string>();
            return report;
        }
    }

    /// <summary>Writes <see cref="OdinValidationReport"/> as UTF-8 JSON, creating parent directories.</summary>
    public static class OdinValidationReportWriter
    {
        public static string Write(string path, OdinValidationReport report)
        {
            string fullPath = Path.GetFullPath(path);
            string directory = Path.GetDirectoryName(fullPath);
            if (!string.IsNullOrEmpty(directory))
                Directory.CreateDirectory(directory);

            string json = JsonUtility.ToJson(report, true) + "\n";
            File.WriteAllText(fullPath, json, new UTF8Encoding(false));
            Debug.Log("[OdinValidator] wrote report to " + fullPath);
            return fullPath;
        }
    }
}
