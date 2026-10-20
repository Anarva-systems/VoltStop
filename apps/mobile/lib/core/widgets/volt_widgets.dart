import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class VoltCard extends StatelessWidget {
  const VoltCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(VoltSpacing.md),
    this.color,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? color;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: padding,
        decoration: BoxDecoration(
          color: color ?? VoltColors.surface,
          borderRadius: BorderRadius.circular(VoltRadii.card),
          border: Border.all(color: VoltColors.border.withValues(alpha: .78)),
          boxShadow: const [
            BoxShadow(
              color: Color(0x0C173B32),
              blurRadius: 18,
              offset: Offset(0, 7),
            ),
          ],
        ),
        child: child,
      );
}

class VoltPageHeading extends StatelessWidget {
  const VoltPageHeading({
    super.key,
    required this.eyebrow,
    required this.title,
    this.subtitle,
    this.trailing,
  });

  final String eyebrow;
  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(eyebrow.toUpperCase(),
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        fontSize: 10,
                        letterSpacing: 1.2,
                        color: VoltColors.muted)),
                const SizedBox(height: 7),
                Text(title,
                    style: Theme.of(context)
                        .textTheme
                        .headlineSmall
                        ?.copyWith(fontSize: 29)),
                if (subtitle != null) ...[
                  const SizedBox(height: 5),
                  Text(subtitle!,
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(color: VoltColors.muted)),
                ],
              ],
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: VoltSpacing.sm),
            trailing!,
          ],
        ],
      );
}

class VoltIconBadge extends StatelessWidget {
  const VoltIconBadge({super.key, required this.icon, this.size = 44});
  final IconData icon;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: VoltColors.elevated,
          borderRadius: BorderRadius.circular(size * .34),
        ),
        child: Icon(icon, color: VoltColors.forest, size: size * .48),
      );
}

class VoltButton extends StatelessWidget {
  const VoltButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.busy = false,
    this.expand = true,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool busy;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final child = busy
        ? const SizedBox(
            width: 19,
            height: 19,
            child: CircularProgressIndicator(
              strokeWidth: 2.2,
              color: VoltColors.surface,
            ),
          )
        : Text(label);
    final button = icon == null
        ? FilledButton(onPressed: busy ? null : onPressed, child: child)
        : FilledButton.icon(
            onPressed: busy ? null : onPressed,
            icon: Icon(icon, size: 19),
            label: child,
          );
    return expand ? SizedBox(width: double.infinity, child: button) : button;
  }
}

class VoltLoading extends StatelessWidget {
  const VoltLoading({super.key, this.label = 'Loading…'});
  final String label;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(VoltSpacing.xl),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                color: VoltColors.forest,
              ),
            ),
            const SizedBox(height: VoltSpacing.sm),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ]),
        ),
      );
}

class VoltError extends StatelessWidget {
  const VoltError({super.key, required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => VoltCard(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.cloud_off_outlined,
              color: VoltColors.warning, size: 30),
          const SizedBox(height: VoltSpacing.xs),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: VoltSpacing.sm),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Try again'),
          ),
        ]),
      );
}

class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.compact = false});
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final markSize = compact ? 27.0 : 34.0;
    return Semantics(
      label: 'VoltStop',
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
          width: markSize,
          height: markSize,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: VoltColors.forest,
            borderRadius: BorderRadius.circular(compact ? 8 : 10),
          ),
          child: Icon(
            Icons.bolt_rounded,
            size: compact ? 18 : 22,
            color: VoltColors.lime,
          ),
        ),
        SizedBox(width: compact ? 8 : 10),
        Text(
          'VOLTSTOP',
          style: TextStyle(
            color: VoltColors.forest,
            fontSize: compact ? 16 : 19,
            fontWeight: FontWeight.w900,
            letterSpacing: compact ? 0.2 : 0.5,
          ),
        ),
      ]),
    );
  }
}
