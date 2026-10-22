using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace ProjectDelta.Editor.DevPlatform
{
    /// <summary>
    /// Reflection-only bridge to the optional Odin Validator package.
    ///
    /// The project does not ship Sirenix assemblies (course rules forbid paid assets and the
    /// Sirenix EULA forbids redistributing the tooling), so no compile-time reference exists
    /// here. Every type, method and result member is resolved by name at runtime. When the
    /// package is absent the bridge reports "skipped" instead of failing the build.
    /// </summary>
    public static class OdinValidatorAdapter
    {
        public const string SessionFullName = "Sirenix.OdinInspector.Editor.Validation.ValidationSession";
        public const string ProfileFullName = "Sirenix.OdinInspector.Editor.Validation.ValidationProfile";
        public const string ResultFullName = "Sirenix.OdinInspector.Editor.Validation.ValidationResult";

        static readonly string[] EntryPointNames =
        {
            "ValidateEverythingEnumerator",
            "ValidateEverything",
            "ValidateAll"
        };

        const int MaxStoredErrors = 50;
        const int MaxStoredWarnings = 20;

        static Dictionary<string, Type> typesByFullName;
        static Dictionary<string, Type> sirenixTypesBySimpleName;

        /// <summary>Probes for Odin Validator and runs it when present. Never throws for absence.</summary>
        public static OdinValidationReport Validate()
        {
            List<string> probed = new List<string>();
            EnsureTypeIndex();

            Type sessionType = Probe(SessionFullName, probed);
            Probe(ProfileFullName, probed);
            Probe(ResultFullName, probed);

            if (sessionType == null)
            {
                return OdinValidationReport.Skipped(
                    "Odin Validator not detected",
                    probed,
                    "Install Odin Inspector + Validator and rerun 'devctl unity odin --require-odin' to validate for real.");
            }

            string detail;
            MethodInfo entryPoint = FindEntryPoint(sessionType, out detail);
            if (entryPoint == null)
                return OdinValidationReport.Error(detail, probed);

            object[] arguments = BuildArguments(entryPoint, out detail);
            if (arguments == null)
                return OdinValidationReport.Error(detail, probed);

            object target;
            try
            {
                target = entryPoint.IsStatic ? null : Activator.CreateInstance(sessionType, true);
            }
            catch (Exception exception)
            {
                return OdinValidationReport.Error(
                    "Could not instantiate " + sessionType.FullName + ": " + exception.Message,
                    probed);
            }

            object sequence = Invoke(entryPoint, target, arguments);
            return Collect(sequence, probed);
        }

        static OdinValidationReport Collect(object sequence, List<string> probed)
        {
            int total = 0;
            int errors = 0;
            int warnings = 0;
            List<string> errorMessages = new List<string>();
            List<string> warningMessages = new List<string>();

            void Consume(object item)
            {
                if (item == null)
                    return;
                total++;
                string severity = ReadSeverity(item);
                string description = Describe(item);
                if (string.Equals(severity, "Error", StringComparison.OrdinalIgnoreCase))
                {
                    errors++;
                    if (errorMessages.Count < MaxStoredErrors)
                        errorMessages.Add(description);
                }
                else if (string.Equals(severity, "Warning", StringComparison.OrdinalIgnoreCase))
                {
                    warnings++;
                    if (warningMessages.Count < MaxStoredWarnings)
                        warningMessages.Add(description);
                }
            }

            if (sequence == null)
                return OdinValidationReport.Completed(0, 0, 0, errorMessages, warningMessages, probed);

            if (sequence is IEnumerator enumerator)
            {
                while (enumerator.MoveNext())
                    Consume(enumerator.Current);
            }
            else if (sequence is IEnumerable enumerable)
            {
                foreach (object item in enumerable)
                    Consume(item);
            }
            else
            {
                Consume(sequence);
            }

            return OdinValidationReport.Completed(total, errors, warnings, errorMessages, warningMessages, probed);
        }

        static MethodInfo FindEntryPoint(Type sessionType, out string detail)
        {
            MethodInfo[] methods = sessionType.GetMethods(
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance);

            foreach (string name in EntryPointNames)
            {
                MethodInfo best = null;
                foreach (MethodInfo method in methods)
                {
                    if (!string.Equals(method.Name, name, StringComparison.Ordinal))
                        continue;
                    if (method.IsGenericMethodDefinition)
                        continue;
                    if (BuildArguments(method, out _) == null)
                        continue;
                    if (best == null || method.GetParameters().Length < best.GetParameters().Length)
                        best = method;
                }

                if (best != null)
                {
                    detail = null;
                    return best;
                }
            }

            detail = "Odin Validator is present but no usable validation entry point was found on "
                + sessionType.FullName + " (tried " + string.Join(", ", EntryPointNames) + ")";
            return null;
        }

        static object[] BuildArguments(MethodInfo method, out string detail)
        {
            ParameterInfo[] parameters = method.GetParameters();
            object[] arguments = new object[parameters.Length];
            for (int i = 0; i < parameters.Length; i++)
            {
                ParameterInfo parameter = parameters[i];
                string name = parameter.Name ?? string.Empty;

                if (parameter.ParameterType.IsByRef)
                {
                    detail = "Unsupported by-ref parameter '" + name + "' on "
                        + method.DeclaringType?.FullName + "." + method.Name;
                    return null;
                }

                if (name.IndexOf("openClosedScenes", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    arguments[i] = true;
                    continue;
                }

                if (name.IndexOf("showProgressBar", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    arguments[i] = false;
                    continue;
                }

                if (parameter.HasDefaultValue)
                {
                    arguments[i] = parameter.DefaultValue;
                    continue;
                }

                if (parameter.ParameterType == typeof(bool))
                {
                    arguments[i] = false;
                    continue;
                }

                if (!parameter.IsOptional && parameter.ParameterType.IsValueType)
                {
                    detail = "Unsupported parameter '" + name + "' (" + parameter.ParameterType.Name
                        + ") on " + method.DeclaringType?.FullName + "." + method.Name;
                    return null;
                }

                arguments[i] = null;
            }

            detail = null;
            return arguments;
        }

        static object Invoke(MethodInfo method, object target, object[] arguments)
        {
            try
            {
                return method.Invoke(target, arguments);
            }
            catch (TargetInvocationException exception) when (exception.InnerException != null)
            {
                throw new InvalidOperationException(
                    "Odin validation threw during " + method.Name + ": " + exception.InnerException.Message,
                    exception.InnerException);
            }
        }

        static string ReadSeverity(object result)
        {
            object severity = ReadMember(result, "Severity");
            if (severity != null)
                return severity.ToString();

            if (ReadMember(result, "IsError") is bool isError && isError)
                return "Error";
            if (ReadMember(result, "IsWarning") is bool isWarning && isWarning)
                return "Warning";
            return string.Empty;
        }

        static string Describe(object result)
        {
            object setup = ReadMember(result, "Setup");

            string message = ReadMember(result, "Message") as string;
            if (string.IsNullOrEmpty(message))
                message = ReadMember(result, "MessageString") as string;
            if (string.IsNullOrEmpty(message) && setup != null)
                message = ReadMember(setup, "Message") as string;
            if (string.IsNullOrEmpty(message))
                message = result.ToString();

            string path = ReadMember(result, "Path") as string;
            if (string.IsNullOrEmpty(path) && setup != null)
                path = ReadMember(setup, "Path") as string;

            return string.IsNullOrEmpty(path) ? message : path + ": " + message;
        }

        static object ReadMember(object target, string name)
        {
            Type type = target.GetType();
            PropertyInfo property = type.GetProperty(
                name,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (property != null && property.GetIndexParameters().Length == 0)
            {
                try
                {
                    return property.GetValue(target);
                }
                catch (Exception)
                {
                    return null;
                }
            }

            FieldInfo field = type.GetField(
                name,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (field != null)
            {
                try
                {
                    return field.GetValue(target);
                }
                catch (Exception)
                {
                    return null;
                }
            }

            return null;
        }

        static Type Probe(string fullName, List<string> probed)
        {
            EnsureTypeIndex();

            if (typesByFullName.TryGetValue(fullName, out Type exact))
            {
                probed.Add(fullName + ": found in " + exact.Assembly.GetName().Name);
                return exact;
            }

            string simpleName = fullName.Substring(fullName.LastIndexOf('.') + 1);
            if (sirenixTypesBySimpleName.TryGetValue(simpleName, out Type fallback))
            {
                probed.Add(fullName + ": not at exact name; resolved " + fallback.FullName
                    + " in " + fallback.Assembly.GetName().Name);
                return fallback;
            }

            probed.Add(fullName + ": not found");
            return null;
        }

        static void EnsureTypeIndex()
        {
            if (typesByFullName != null)
                return;

            typesByFullName = new Dictionary<string, Type>(StringComparer.Ordinal);
            sirenixTypesBySimpleName = new Dictionary<string, Type>(StringComparer.Ordinal);

            foreach (Assembly assembly in SafeAssemblies())
            {
                AssemblyName assemblyName = assembly.GetName();
                bool sirenix = assemblyName.Name != null
                    && assemblyName.Name.StartsWith("Sirenix", StringComparison.OrdinalIgnoreCase);

                foreach (Type type in SafeTypes(assembly))
                {
                    if (type == null || string.IsNullOrEmpty(type.FullName))
                        continue;
                    typesByFullName[type.FullName] = type;
                    if (sirenix && !string.IsNullOrEmpty(type.Name))
                        sirenixTypesBySimpleName[type.Name] = type;
                }
            }
        }

        static Assembly[] SafeAssemblies()
        {
            try
            {
                return AppDomain.CurrentDomain.GetAssemblies();
            }
            catch (Exception exception)
            {
                Debug.LogWarning("[OdinValidator] assembly enumeration failed: " + exception.Message);
                return Array.Empty<Assembly>();
            }
        }

        static Type[] SafeTypes(Assembly assembly)
        {
            try
            {
                return assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException exception)
            {
                List<Type> loaded = new List<Type>();
                if (exception.Types != null)
                {
                    foreach (Type type in exception.Types)
                    {
                        if (type != null)
                            loaded.Add(type);
                    }
                }
                return loaded.ToArray();
            }
            catch (Exception)
            {
                return Array.Empty<Type>();
            }
        }
    }
}
