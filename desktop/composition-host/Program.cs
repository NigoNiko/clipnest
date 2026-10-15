using System;
using System.IO;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Media;
using Avalonia.Win32;
using Avalonia.Threading;

namespace ClipNest.BlurHost;

internal static class Program
{
    internal static string WindowTitle { get; private set; } = "ClipNest blur host";
    internal static string? StatusPath { get; private set; }

    [STAThread]
    private static void Main(string[] args)
    {
        foreach (var arg in args)
        {
            if (arg.StartsWith("--title=", StringComparison.Ordinal))
                WindowTitle = arg[8..];
            if (arg.StartsWith("--status=", StringComparison.Ordinal))
                StatusPath = arg[9..];
        }

        AppBuilder.Configure<BlurHostApp>()
            .UsePlatformDetect()
            .With(new Win32PlatformOptions
            {
                RenderingMode = [Win32RenderingMode.AngleEgl, Win32RenderingMode.Software],
                CompositionMode = [Win32CompositionMode.WinUIComposition, Win32CompositionMode.RedirectionSurface],
                // The host sits two physical pixels inside the Qt window.
                WinUICompositionBackdropCornerRadius = 20f,
            })
            .StartWithClassicDesktopLifetime(args);
    }
}

internal sealed class BlurHostApp : Application
{
    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var window = new Window
            {
                Title = Program.WindowTitle,
                Width = 8,
                Height = 8,
                Position = new PixelPoint(-32000, -32000),
                CanResize = false,
                ShowActivated = false,
                ShowInTaskbar = false,
                Topmost = true,
                WindowDecorations = WindowDecorations.None,
                Background = Brushes.Transparent,
                TransparencyBackgroundFallback = Brushes.Transparent,
                TransparencyLevelHint = [WindowTransparencyLevel.AcrylicBlur],
                Content = new Border { Background = Brushes.Transparent },
            };
            void ReportStatus(string status)
            {
                if (Program.StatusPath is not { } path)
                    return;
                try { File.WriteAllText(path, status); }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
            window.PropertyChanged += (_, e) =>
            {
                if (e.Property.Name == nameof(Window.ActualTransparencyLevel) &&
                    window.ActualTransparencyLevel == WindowTransparencyLevel.AcrylicBlur)
                    ReportStatus("acrylic");
            };
            window.Opened += async (_, _) =>
            {
                await Task.Delay(350);
                Dispatcher.UIThread.Post(() => ReportStatus(
                    window.ActualTransparencyLevel == WindowTransparencyLevel.AcrylicBlur
                        ? "acrylic" : "fallback"));
            };
            desktop.MainWindow = window;
        }

        base.OnFrameworkInitializationCompleted();
    }
}
