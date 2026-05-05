// dart format width=80
// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'count.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$StateUpdate {
  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType && other is StateUpdate);
  }

  @override
  int get hashCode => runtimeType.hashCode;

  @override
  String toString() {
    return 'StateUpdate()';
  }
}

/// @nodoc

class StateUpdate_BatchFetch extends StateUpdate {
  const StateUpdate_BatchFetch({required this.batch}) : super._();

  final Batch batch;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @pragma('vm:prefer-inline')
  $StateUpdate_BatchFetchCopyWith<StateUpdate_BatchFetch> get copyWith =>
      _$StateUpdate_BatchFetchCopyWithImpl<StateUpdate_BatchFetch>(
          this, _$identity);

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is StateUpdate_BatchFetch &&
            (identical(other.batch, batch) || other.batch == batch));
  }

  @override
  int get hashCode => Object.hash(runtimeType, batch);

  @override
  String toString() {
    return 'StateUpdate.batchFetch(batch: $batch)';
  }
}

/// @nodoc
abstract mixin class $StateUpdate_BatchFetchCopyWith<$Res> {
  factory $StateUpdate_BatchFetchCopyWith(StateUpdate_BatchFetch value,
          $Res Function(StateUpdate_BatchFetch) _then) =
      _$StateUpdate_BatchFetchCopyWithImpl;
  @useResult
  $Res call({Batch batch});
}

/// @nodoc
class _$StateUpdate_BatchFetchCopyWithImpl<$Res>
    implements $StateUpdate_BatchFetchCopyWith<$Res> {
  _$StateUpdate_BatchFetchCopyWithImpl(this._self, this._then);

  final StateUpdate_BatchFetch _self;
  final $Res Function(StateUpdate_BatchFetch) _then;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  $Res call({
    Object? batch = null,
  }) {
    return _then(StateUpdate_BatchFetch(
      batch: null == batch
          ? _self.batch
          : batch // ignore: cast_nullable_to_non_nullable
              as Batch,
    ));
  }
}

/// @nodoc

class StateUpdate_BatchGlobalState extends StateUpdate {
  const StateUpdate_BatchGlobalState({required this.batchGlobalState})
      : super._();

  final BatchGlobalState batchGlobalState;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @pragma('vm:prefer-inline')
  $StateUpdate_BatchGlobalStateCopyWith<StateUpdate_BatchGlobalState>
      get copyWith => _$StateUpdate_BatchGlobalStateCopyWithImpl<
          StateUpdate_BatchGlobalState>(this, _$identity);

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is StateUpdate_BatchGlobalState &&
            (identical(other.batchGlobalState, batchGlobalState) ||
                other.batchGlobalState == batchGlobalState));
  }

  @override
  int get hashCode => Object.hash(runtimeType, batchGlobalState);

  @override
  String toString() {
    return 'StateUpdate.batchGlobalState(batchGlobalState: $batchGlobalState)';
  }
}

/// @nodoc
abstract mixin class $StateUpdate_BatchGlobalStateCopyWith<$Res> {
  factory $StateUpdate_BatchGlobalStateCopyWith(
          StateUpdate_BatchGlobalState value,
          $Res Function(StateUpdate_BatchGlobalState) _then) =
      _$StateUpdate_BatchGlobalStateCopyWithImpl;
  @useResult
  $Res call({BatchGlobalState batchGlobalState});
}

/// @nodoc
class _$StateUpdate_BatchGlobalStateCopyWithImpl<$Res>
    implements $StateUpdate_BatchGlobalStateCopyWith<$Res> {
  _$StateUpdate_BatchGlobalStateCopyWithImpl(this._self, this._then);

  final StateUpdate_BatchGlobalState _self;
  final $Res Function(StateUpdate_BatchGlobalState) _then;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  $Res call({
    Object? batchGlobalState = null,
  }) {
    return _then(StateUpdate_BatchGlobalState(
      batchGlobalState: null == batchGlobalState
          ? _self.batchGlobalState
          : batchGlobalState // ignore: cast_nullable_to_non_nullable
              as BatchGlobalState,
    ));
  }
}

/// @nodoc

class StateUpdate_ButtonPressed extends StateUpdate {
  const StateUpdate_ButtonPressed({required this.buttonId}) : super._();

  final int buttonId;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @pragma('vm:prefer-inline')
  $StateUpdate_ButtonPressedCopyWith<StateUpdate_ButtonPressed> get copyWith =>
      _$StateUpdate_ButtonPressedCopyWithImpl<StateUpdate_ButtonPressed>(
          this, _$identity);

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is StateUpdate_ButtonPressed &&
            (identical(other.buttonId, buttonId) ||
                other.buttonId == buttonId));
  }

  @override
  int get hashCode => Object.hash(runtimeType, buttonId);

  @override
  String toString() {
    return 'StateUpdate.buttonPressed(buttonId: $buttonId)';
  }
}

/// @nodoc
abstract mixin class $StateUpdate_ButtonPressedCopyWith<$Res> {
  factory $StateUpdate_ButtonPressedCopyWith(StateUpdate_ButtonPressed value,
          $Res Function(StateUpdate_ButtonPressed) _then) =
      _$StateUpdate_ButtonPressedCopyWithImpl;
  @useResult
  $Res call({int buttonId});
}

/// @nodoc
class _$StateUpdate_ButtonPressedCopyWithImpl<$Res>
    implements $StateUpdate_ButtonPressedCopyWith<$Res> {
  _$StateUpdate_ButtonPressedCopyWithImpl(this._self, this._then);

  final StateUpdate_ButtonPressed _self;
  final $Res Function(StateUpdate_ButtonPressed) _then;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  $Res call({
    Object? buttonId = null,
  }) {
    return _then(StateUpdate_ButtonPressed(
      buttonId: null == buttonId
          ? _self.buttonId
          : buttonId // ignore: cast_nullable_to_non_nullable
              as int,
    ));
  }
}

/// @nodoc

class StateUpdate_PipelineStateUpdate extends StateUpdate {
  const StateUpdate_PipelineStateUpdate(
      {required this.newState, this.error, this.debug})
      : super._();

  final PipelineState newState;
  final String? error;
  final String? debug;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @pragma('vm:prefer-inline')
  $StateUpdate_PipelineStateUpdateCopyWith<StateUpdate_PipelineStateUpdate>
      get copyWith => _$StateUpdate_PipelineStateUpdateCopyWithImpl<
          StateUpdate_PipelineStateUpdate>(this, _$identity);

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is StateUpdate_PipelineStateUpdate &&
            (identical(other.newState, newState) ||
                other.newState == newState) &&
            (identical(other.error, error) || other.error == error) &&
            (identical(other.debug, debug) || other.debug == debug));
  }

  @override
  int get hashCode => Object.hash(runtimeType, newState, error, debug);

  @override
  String toString() {
    return 'StateUpdate.pipelineStateUpdate(newState: $newState, error: $error, debug: $debug)';
  }
}

/// @nodoc
abstract mixin class $StateUpdate_PipelineStateUpdateCopyWith<$Res> {
  factory $StateUpdate_PipelineStateUpdateCopyWith(
          StateUpdate_PipelineStateUpdate value,
          $Res Function(StateUpdate_PipelineStateUpdate) _then) =
      _$StateUpdate_PipelineStateUpdateCopyWithImpl;
  @useResult
  $Res call({PipelineState newState, String? error, String? debug});
}

/// @nodoc
class _$StateUpdate_PipelineStateUpdateCopyWithImpl<$Res>
    implements $StateUpdate_PipelineStateUpdateCopyWith<$Res> {
  _$StateUpdate_PipelineStateUpdateCopyWithImpl(this._self, this._then);

  final StateUpdate_PipelineStateUpdate _self;
  final $Res Function(StateUpdate_PipelineStateUpdate) _then;

  /// Create a copy of StateUpdate
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  $Res call({
    Object? newState = null,
    Object? error = freezed,
    Object? debug = freezed,
  }) {
    return _then(StateUpdate_PipelineStateUpdate(
      newState: null == newState
          ? _self.newState
          : newState // ignore: cast_nullable_to_non_nullable
              as PipelineState,
      error: freezed == error
          ? _self.error
          : error // ignore: cast_nullable_to_non_nullable
              as String?,
      debug: freezed == debug
          ? _self.debug
          : debug // ignore: cast_nullable_to_non_nullable
              as String?,
    ));
  }
}

/// @nodoc

class StateUpdate_StopConfirmationUpdate extends StateUpdate {
  const StateUpdate_StopConfirmationUpdate() : super._();

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is StateUpdate_StopConfirmationUpdate);
  }

  @override
  int get hashCode => runtimeType.hashCode;

  @override
  String toString() {
    return 'StateUpdate.stopConfirmationUpdate()';
  }
}

// dart format on
