import { useRef, useState } from 'react';
import { Platform, Pressable, TextInput, View, type TextInputInstance } from 'react-native';
import { C, F, R } from './theme';
import { T } from './ui';

const LENGTH = 6;

/* The six code boxes after a mobile number is entered. They are one real field underneath, so the code can be typed
   or pasted, and the phone offers it straight from the SMS (iOS's one-time-code, Android's SMS autofill). In a
   development build the code arrives already filled in. */
export function Otp({ code, onChange }: { code: string; onChange: (code: string) => void }) {
  const input = useRef<TextInputInstance>(null);
  const [focused, setFocused] = useState(false);
  const digits = code.replace(/\D/g, '').slice(0, LENGTH);
  return (
    <Pressable onPress={() => input.current?.focus()} accessible={false} style={{ alignSelf: 'center' }}>
      <View style={{ flexDirection: 'row', gap: 6 }}>
        {Array.from({ length: LENGTH }, (_, k) => {
          const next = focused && k === Math.min(digits.length, LENGTH - 1);
          return (
            <View key={k} style={{ width: 42, height: 50, borderRadius: R.sm, borderWidth: next ? 2 : 1, borderColor: next ? C.accent : C.line, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' }}>
              <T v="h3" style={{ color: digits[k] ? C.ink : C.line }}>{digits[k] ?? '·'}</T>
            </View>
          );
        })}
      </View>
      {/* the real field sits over the boxes, invisible: tapping anywhere on them types into it */}
      <TextInput ref={input} value={digits} onChangeText={t => onChange(t.replace(/\D/g, '').slice(0, LENGTH))}
        keyboardType="number-pad" maxLength={LENGTH} textContentType="oneTimeCode" autoComplete={Platform.OS === 'android' ? 'sms-otp' : 'one-time-code'}
        accessibilityLabel={`${LENGTH}-digit code`} caretHidden selectionColor="transparent" underlineColorAndroid="transparent"
        onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, opacity: 0.011, color: 'transparent', fontFamily: F.semi }} />
    </Pressable>
  );
}
